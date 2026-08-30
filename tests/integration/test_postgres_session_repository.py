from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)
from aeroeyes_monitoring_api.session_repository import DuplicateSessionError

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
STARTED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def active_session() -> MonitoringSession:
    return MonitoringSession(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        started_at=STARTED_AT,
    )


def test_add_and_get(db_session: Session) -> None:
    repository = PostgresSessionRepository(db_session)
    expected = active_session()

    repository.add(expected)

    assert repository.get(SESSION_ID) == expected


def test_duplicate_session_id_raises_without_poisoning_transaction(
    db_session: Session,
) -> None:
    repository = PostgresSessionRepository(db_session)
    expected = active_session()

    with db_session.begin():
        repository.add(expected)
        with pytest.raises(DuplicateSessionError):
            repository.add(expected)
        assert repository.get(SESSION_ID) == expected


def test_get_missing_returns_none(db_session: Session) -> None:
    repository = PostgresSessionRepository(db_session)

    assert repository.get(uuid4()) is None


def test_complete_active_session(db_session: Session) -> None:
    repository = PostgresSessionRepository(db_session)
    repository.add(active_session())
    completed_at = STARTED_AT + timedelta(minutes=30)

    completed = repository.complete(SESSION_ID, completed_at)

    assert completed is not None
    assert completed.status is SessionStatus.COMPLETED
    assert completed.ended_at == completed_at
    assert repository.get(SESSION_ID) == completed


def test_repeated_completion_preserves_first_ended_at(
    db_session: Session,
) -> None:
    repository = PostgresSessionRepository(db_session)
    repository.add(active_session())
    first_completion = STARTED_AT + timedelta(minutes=30)

    repository.complete(SESSION_ID, first_completion)
    repeated = repository.complete(
        SESSION_ID,
        first_completion + timedelta(minutes=5),
    )

    assert repeated is not None
    assert repeated.ended_at == first_completion


def test_completion_before_start_preserves_domain_validation(
    db_session: Session,
) -> None:
    repository = PostgresSessionRepository(db_session)
    repository.add(active_session())

    with pytest.raises(ValueError, match="earlier than started_at"):
        repository.complete(
            SESSION_ID,
            STARTED_AT - timedelta(microseconds=1),
        )

    assert repository.get(SESSION_ID) == active_session()


def test_data_survives_repository_reconstruction_and_new_session(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as first_session:
        with first_session.begin():
            PostgresSessionRepository(first_session).add(active_session())

    with Session(postgres_engine) as second_session:
        reconstructed = PostgresSessionRepository(second_session)
        assert reconstructed.get(SESSION_ID) == active_session()


def test_repository_leaves_commit_to_caller(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as writer, Session(postgres_engine) as reader:
        PostgresSessionRepository(writer).add(active_session())

        assert PostgresSessionRepository(reader).get(SESSION_ID) is None

        writer.commit()

        assert PostgresSessionRepository(reader).get(SESSION_ID) == active_session()


def test_simultaneous_completion_has_one_winner_observed_by_both_callers(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as setup_session:
        with setup_session.begin():
            PostgresSessionRepository(setup_session).add(active_session())

    completion_times = (
        STARTED_AT + timedelta(minutes=30),
        STARTED_AT + timedelta(minutes=31),
    )
    barrier = Barrier(2)

    def complete(completed_at: datetime) -> MonitoringSession | None:
        with Session(postgres_engine) as independent_session:
            with independent_session.begin():
                barrier.wait()
                return PostgresSessionRepository(independent_session).complete(
                    SESSION_ID,
                    completed_at,
                )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(complete, completion_times))

    assert results[0] is not None
    assert results[1] is not None
    assert results[0].ended_at == results[1].ended_at
    assert results[0].ended_at in completion_times

    with Session(postgres_engine) as verification_session:
        persisted = PostgresSessionRepository(verification_session).get(SESSION_ID)
        assert persisted is not None
        assert persisted.ended_at == results[0].ended_at
