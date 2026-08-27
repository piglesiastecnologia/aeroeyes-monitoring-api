from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.session_repository import (
    DuplicateSessionError,
    InMemorySessionRepository,
)

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
STARTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def active_session() -> MonitoringSession:
    return MonitoringSession(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        started_at=STARTED_AT,
    )


def test_stored_session_can_be_retrieved() -> None:
    repository = InMemorySessionRepository()
    session = active_session()

    repository.add(session)

    assert repository.get(SESSION_ID) == session


def test_unknown_session_returns_none() -> None:
    repository = InMemorySessionRepository()
    unknown_id = uuid4()

    assert repository.get(unknown_id) is None
    assert repository.complete(unknown_id, STARTED_AT) is None


def test_completion_is_persisted() -> None:
    repository = InMemorySessionRepository()
    repository.add(active_session())
    completed_at = STARTED_AT + timedelta(minutes=30)

    completed = repository.complete(SESSION_ID, completed_at)

    assert completed is not None
    assert completed.status is SessionStatus.COMPLETED
    assert completed.ended_at == completed_at
    assert repository.get(SESSION_ID) == completed


def test_repeated_completion_preserves_first_end_time() -> None:
    repository = InMemorySessionRepository()
    repository.add(active_session())
    first_completion = STARTED_AT + timedelta(minutes=30)

    repository.complete(SESSION_ID, first_completion)
    repeated = repository.complete(
        SESSION_ID,
        first_completion + timedelta(minutes=5),
    )

    assert repeated is not None
    assert repeated.ended_at == first_completion


def test_duplicate_session_id_is_rejected_without_replacing_session() -> None:
    repository = InMemorySessionRepository()
    session = active_session()
    repository.add(session)

    with pytest.raises(DuplicateSessionError):
        repository.add(session)

    assert repository.get(SESSION_ID) is session


def test_concurrent_completion_preserves_one_winning_timestamp() -> None:
    repository = InMemorySessionRepository()
    repository.add(active_session())
    completion_times = (
        STARTED_AT + timedelta(minutes=30),
        STARTED_AT + timedelta(minutes=31),
    )
    barrier = Barrier(2)

    def complete(completed_at: datetime) -> MonitoringSession | None:
        barrier.wait()
        return repository.complete(SESSION_ID, completed_at)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(complete, completion_times))

    assert results[0] is not None
    assert results[1] is not None
    assert results[0].ended_at == results[1].ended_at
    assert results[0].ended_at in completion_times
    assert repository.get(SESSION_ID).ended_at == results[0].ended_at
