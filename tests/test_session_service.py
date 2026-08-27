from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import (
    SessionNotFoundError,
    SessionService,
)

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
STARTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def test_create_uses_injected_identity_and_clock() -> None:
    service = SessionService(
        InMemorySessionRepository(),
        clock=lambda: STARTED_AT,
        session_id_factory=lambda: SESSION_ID,
    )

    session = service.create_session()

    assert session.session_id == SESSION_ID
    assert session.started_at == STARTED_AT
    assert session.status is SessionStatus.ACTIVE


def test_unknown_session_raises_not_found() -> None:
    service = SessionService(InMemorySessionRepository())

    with pytest.raises(SessionNotFoundError):
        service.get_session(uuid4())

    with pytest.raises(SessionNotFoundError):
        service.complete_session(uuid4())


def test_completion_uses_injected_clock() -> None:
    repository = InMemorySessionRepository()
    repository.add(
        MonitoringSession(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            started_at=STARTED_AT,
        )
    )
    completed_at = STARTED_AT + timedelta(minutes=30)
    service = SessionService(repository, clock=lambda: completed_at)

    completed = service.complete_session(SESSION_ID)

    assert completed.ended_at == completed_at


def test_repeated_completion_preserves_first_result() -> None:
    times = iter(
        (
            STARTED_AT,
            STARTED_AT + timedelta(minutes=30),
            STARTED_AT + timedelta(minutes=35),
        )
    )
    service = SessionService(
        InMemorySessionRepository(),
        clock=lambda: next(times),
        session_id_factory=lambda: SESSION_ID,
    )
    session = service.create_session()

    first = service.complete_session(session.session_id)
    repeated = service.complete_session(session.session_id)

    assert repeated == first
    assert repeated.ended_at == STARTED_AT + timedelta(minutes=30)
