from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
    IngestedAttentionEvent,
)
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.event_repository import EventAcceptanceStatus
from aeroeyes_monitoring_api.persistence.models import AttentionEventRecord
from aeroeyes_monitoring_api.persistence.postgres_event_repository import (
    PostgresEventRepository,
)
from aeroeyes_monitoring_api.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)

EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000010")
SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
STARTED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
OCCURRED_AT = STARTED_AT + timedelta(minutes=10)
RECEIVED_AT = STARTED_AT + timedelta(minutes=11)


def event(**changes: object) -> IngestedAttentionEvent:
    values = {
        "event_id": EVENT_ID,
        "session_id": SESSION_ID,
        "occurred_at": OCCURRED_AT,
        "received_at": RECEIVED_AT,
        "state": AttentionState.ATTENTION,
        "severity": AttentionSeverity.MEDIUM,
        "face_detected": True,
        "eye_state": EyeState.CLOSED,
        "closed_duration_ms": 1250,
        "schema_version": 1,
    }
    values.update(changes)
    return IngestedAttentionEvent(**values)


def add_monitoring_session(session: Session) -> None:
    PostgresSessionRepository(session).add(
        MonitoringSession(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            started_at=STARTED_AT,
        )
    )


def test_first_event_is_accepted_and_persisted(db_session: Session) -> None:
    add_monitoring_session(db_session)
    repository = PostgresEventRepository(db_session)
    candidate = event()

    result = repository.accept(candidate)

    assert result.status is EventAcceptanceStatus.CREATED
    assert result.event is candidate
    assert repository.resolve_existing(candidate) is not None


def test_resolve_existing_replay_preserves_original_received_at(
    db_session: Session,
) -> None:
    add_monitoring_session(db_session)
    repository = PostgresEventRepository(db_session)
    original = event()
    replay = replace(original, received_at=RECEIVED_AT + timedelta(minutes=1))
    repository.accept(original)

    result = repository.resolve_existing(replay)

    assert result is not None
    assert result.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert result.event == original
    assert result.event.received_at == RECEIVED_AT


def test_same_event_id_with_different_semantics_conflicts(
    db_session: Session,
) -> None:
    add_monitoring_session(db_session)
    repository = PostgresEventRepository(db_session)
    original = event()
    repository.accept(original)

    result = repository.accept(
        replace(original, state=AttentionState.CRITICAL)
    )

    assert result.status is EventAcceptanceStatus.CONFLICT
    assert result.event == original


def test_event_survives_repository_reconstruction_and_new_session(
    postgres_engine: Engine,
) -> None:
    expected = event()
    with Session(postgres_engine) as first_session:
        with first_session.begin():
            add_monitoring_session(first_session)
            PostgresEventRepository(first_session).accept(expected)

    with Session(postgres_engine) as second_session:
        result = PostgresEventRepository(second_session).resolve_existing(expected)

    assert result is not None
    assert result.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert result.event == expected
    assert result.event.occurred_at.tzinfo is timezone.utc
    assert result.event.received_at.tzinfo is timezone.utc


def test_repository_leaves_commit_to_caller(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as setup_session:
        with setup_session.begin():
            add_monitoring_session(setup_session)

    candidate = event()
    with Session(postgres_engine) as writer, Session(postgres_engine) as reader:
        PostgresEventRepository(writer).accept(candidate)

        assert PostgresEventRepository(reader).resolve_existing(candidate) is None

        writer.rollback()

    with Session(postgres_engine) as verification_session:
        assert (
            PostgresEventRepository(verification_session).resolve_existing(candidate)
            is None
        )


def test_two_simultaneous_identical_events_have_one_winner(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as setup_session:
        with setup_session.begin():
            add_monitoring_session(setup_session)

    candidates = (
        event(received_at=RECEIVED_AT),
        event(received_at=RECEIVED_AT + timedelta(seconds=1)),
    )
    barrier = Barrier(2)

    def accept(candidate: IngestedAttentionEvent):
        with Session(postgres_engine) as independent_session:
            with independent_session.begin():
                barrier.wait()
                return PostgresEventRepository(independent_session).accept(candidate)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(accept, candidates))

    statuses = [result.status for result in results]
    assert statuses.count(EventAcceptanceStatus.CREATED) == 1
    assert statuses.count(EventAcceptanceStatus.ALREADY_PROCESSED) == 1
    assert results[0].event == results[1].event
    winner = next(
        result.event
        for result in results
        if result.status is EventAcceptanceStatus.CREATED
    )
    assert all(result.event.received_at == winner.received_at for result in results)

    with Session(postgres_engine) as verification_session:
        row_count = verification_session.scalar(
            select(func.count()).select_from(AttentionEventRecord)
        )
    assert row_count == 1


def test_two_simultaneous_conflicting_events_keep_one_winner(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as setup_session:
        with setup_session.begin():
            add_monitoring_session(setup_session)

    candidates = (
        event(state=AttentionState.ATTENTION),
        event(
            state=AttentionState.CRITICAL,
            received_at=RECEIVED_AT + timedelta(seconds=1),
        ),
    )
    barrier = Barrier(2)

    def accept(candidate: IngestedAttentionEvent):
        with Session(postgres_engine) as independent_session:
            with independent_session.begin():
                barrier.wait()
                return PostgresEventRepository(independent_session).accept(candidate)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(accept, candidates))

    assert {result.status for result in results} == {
        EventAcceptanceStatus.CREATED,
        EventAcceptanceStatus.CONFLICT,
    }
    winner = next(
        result.event
        for result in results
        if result.status is EventAcceptanceStatus.CREATED
    )
    assert all(result.event == winner for result in results)

    with Session(postgres_engine) as verification_session:
        row_count = verification_session.scalar(
            select(func.count()).select_from(AttentionEventRecord)
        )
    assert row_count == 1
