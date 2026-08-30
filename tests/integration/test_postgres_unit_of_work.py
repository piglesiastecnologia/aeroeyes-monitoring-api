from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

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
from aeroeyes_monitoring_api.persistence.database import create_session_factory
from aeroeyes_monitoring_api.persistence.models import (
    AttentionEventRecord,
    MonitoringSessionRecord,
)
from aeroeyes_monitoring_api.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)
from aeroeyes_monitoring_api.persistence.postgres_unit_of_work import (
    PostgresUnitOfWork,
)

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000010")
STARTED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
COMPLETED_AT = STARTED_AT + timedelta(minutes=30)


def active_session() -> MonitoringSession:
    return MonitoringSession(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        started_at=STARTED_AT,
    )


def attention_event() -> IngestedAttentionEvent:
    return IngestedAttentionEvent(
        event_id=EVENT_ID,
        session_id=SESSION_ID,
        occurred_at=STARTED_AT + timedelta(minutes=10),
        received_at=STARTED_AT + timedelta(minutes=11),
        state=AttentionState.ATTENTION,
        severity=AttentionSeverity.MEDIUM,
        face_detected=True,
        eye_state=EyeState.CLOSED,
        closed_duration_ms=1250,
        schema_version=1,
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def seed_session(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        PostgresSessionRepository(session).add(active_session())


def test_repositories_are_available_only_inside_active_unit_of_work(
    postgres_engine: Engine,
) -> None:
    uow = PostgresUnitOfWork(session_factory(postgres_engine))

    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        _ = uow.sessions
    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        _ = uow.events

    with uow:
        assert uow.sessions is not None
        assert uow.events is not None

    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        _ = uow.sessions
    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        _ = uow.events


def test_repositories_share_one_sqlalchemy_session_and_transaction(
    postgres_engine: Engine,
) -> None:
    with PostgresUnitOfWork(session_factory(postgres_engine)) as uow:
        assert uow.sessions._session is uow.events._session

        uow.sessions.add(active_session())
        result = uow.events.accept(attention_event())

        assert result.status is EventAcceptanceStatus.CREATED
        uow.commit()


def test_commit_persists_changes_from_both_repositories(
    postgres_engine: Engine,
) -> None:
    with PostgresUnitOfWork(session_factory(postgres_engine)) as uow:
        uow.sessions.add(active_session())
        uow.events.accept(attention_event())
        uow.commit()

    with Session(postgres_engine) as verification:
        assert verification.scalar(
            select(func.count()).select_from(MonitoringSessionRecord)
        ) == 1
        assert verification.scalar(
            select(func.count()).select_from(AttentionEventRecord)
        ) == 1


def test_explicit_rollback_removes_all_pending_changes(
    postgres_engine: Engine,
) -> None:
    with PostgresUnitOfWork(session_factory(postgres_engine)) as uow:
        uow.sessions.add(active_session())
        uow.events.accept(attention_event())
        uow.rollback()

    with Session(postgres_engine) as verification:
        assert verification.get(MonitoringSessionRecord, SESSION_ID) is None
        assert verification.get(AttentionEventRecord, EVENT_ID) is None


def test_exit_without_commit_does_not_persist_changes(
    postgres_engine: Engine,
) -> None:
    with PostgresUnitOfWork(session_factory(postgres_engine)) as uow:
        uow.sessions.add(active_session())
        uow.events.accept(attention_event())

    with Session(postgres_engine) as verification:
        assert verification.get(MonitoringSessionRecord, SESSION_ID) is None
        assert verification.get(AttentionEventRecord, EVENT_ID) is None


def test_exception_rolls_back_and_closes_session_cleanly(
    postgres_engine: Engine,
) -> None:
    closed_sessions: list[Session] = []

    class TrackingSession(Session):
        def close(self) -> None:
            super().close()
            closed_sessions.append(self)

    tracking_factory = sessionmaker(
        bind=postgres_engine,
        class_=TrackingSession,
        expire_on_commit=False,
    )

    with pytest.raises(RuntimeError, match="test failure"):
        with PostgresUnitOfWork(tracking_factory) as uow:
            uow.sessions.add(active_session())
            raise RuntimeError("test failure")

    assert len(closed_sessions) == 1
    assert not closed_sessions[0].in_transaction()
    with Session(postgres_engine) as verification:
        assert verification.get(MonitoringSessionRecord, SESSION_ID) is None


def test_get_for_event_ingestion_returns_domain_session(
    postgres_engine: Engine,
) -> None:
    seed_session(postgres_engine)

    with PostgresUnitOfWork(session_factory(postgres_engine)) as uow:
        assert uow.sessions.get_for_event_ingestion(SESSION_ID) == active_session()
        uow.commit()


def test_ingestion_shared_lock_prevents_completion_until_release(
    postgres_engine: Engine,
) -> None:
    seed_session(postgres_engine)
    lock_acquired = Event()
    release_lock = Event()
    ingestion_errors: list[BaseException] = []

    def hold_ingestion_lock() -> None:
        try:
            with PostgresUnitOfWork(session_factory(postgres_engine)) as uow:
                assert (
                    uow.sessions.get_for_event_ingestion(SESSION_ID)
                    == active_session()
                )
                lock_acquired.set()
                if not release_lock.wait(timeout=5):
                    raise TimeoutError("test did not release ingestion lock")
                uow.commit()
        except BaseException as exc:
            ingestion_errors.append(exc)
            lock_acquired.set()

    ingestion_thread = Thread(target=hold_ingestion_lock)
    ingestion_thread.start()
    assert lock_acquired.wait(timeout=5)

    try:
        with Session(postgres_engine) as completion_session:
            completion_session.execute(text("SET LOCAL lock_timeout = '250ms'"))
            with pytest.raises(OperationalError):
                PostgresSessionRepository(completion_session).complete(
                    SESSION_ID,
                    COMPLETED_AT,
                )
            completion_session.rollback()
    finally:
        release_lock.set()
        ingestion_thread.join(timeout=5)

    assert not ingestion_thread.is_alive()
    assert ingestion_errors == []

    with Session(postgres_engine) as completion_session:
        with completion_session.begin():
            completed = PostgresSessionRepository(completion_session).complete(
                SESSION_ID,
                COMPLETED_AT,
            )
    assert completed is not None
    assert completed.status is SessionStatus.COMPLETED


def test_completion_wins_then_shared_read_observes_completed_session(
    postgres_engine: Engine,
) -> None:
    seed_session(postgres_engine)

    with Session(postgres_engine) as completion_session:
        completed = PostgresSessionRepository(completion_session).complete(
            SESSION_ID,
            COMPLETED_AT,
        )
        completion_session.commit()

    assert completed is not None
    assert completed.status is SessionStatus.COMPLETED

    with PostgresUnitOfWork(session_factory(postgres_engine)) as uow:
        observed = uow.sessions.get_for_event_ingestion(SESSION_ID)
        uow.commit()

    assert observed == completed
    assert observed is not None
    assert observed.status is SessionStatus.COMPLETED
