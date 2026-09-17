from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import (
    SessionNotFoundError,
    SessionService,
)
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
STARTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def service_for(
    repository: InMemorySessionRepository | None = None,
    **kwargs,
) -> SessionService:
    sessions = repository or InMemorySessionRepository()
    events = InMemoryEventRepository()
    contexts = InMemorySessionContextRepository()
    return SessionService(
        lambda: InMemoryUnitOfWork(sessions, events, contexts),
        **kwargs,
    )


def test_create_uses_injected_identity_and_clock() -> None:
    service = service_for(
        clock=lambda: STARTED_AT,
        session_id_factory=lambda: SESSION_ID,
    )

    session = service.create_session()

    assert session.session_id == SESSION_ID
    assert session.started_at == STARTED_AT
    assert session.status is SessionStatus.ACTIVE


def test_unknown_session_raises_not_found() -> None:
    service = service_for()

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
    service = service_for(repository, clock=lambda: completed_at)

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
    service = service_for(
        clock=lambda: next(times),
        session_id_factory=lambda: SESSION_ID,
    )
    session = service.create_session()

    first = service.complete_session(session.session_id)
    repeated = service.complete_session(session.session_id)

    assert repeated == first
    assert repeated.ended_at == STARTED_AT + timedelta(minutes=30)


def test_each_operation_uses_a_fresh_unit_of_work_and_commits_writes() -> None:
    sessions = InMemorySessionRepository()
    events = InMemoryEventRepository()
    contexts = InMemorySessionContextRepository()

    class RecordingUnitOfWork(InMemoryUnitOfWork):
        def __init__(self) -> None:
            super().__init__(sessions, events, contexts)
            self.commit_count = 0

        def commit(self) -> None:
            self.commit_count += 1

    created_uows: list[RecordingUnitOfWork] = []

    def unit_of_work_factory() -> RecordingUnitOfWork:
        uow = RecordingUnitOfWork()
        created_uows.append(uow)
        return uow

    completed_at = STARTED_AT + timedelta(minutes=30)
    times = iter((STARTED_AT, completed_at))
    service = SessionService(
        unit_of_work_factory,
        clock=lambda: next(times),
        session_id_factory=lambda: SESSION_ID,
    )

    created = service.create_session()
    retrieved = service.get_session(created.session_id)
    completed = service.complete_session(created.session_id)

    assert retrieved == created
    assert completed.ended_at == completed_at
    assert len(created_uows) == 3
    assert [uow.commit_count for uow in created_uows] == [1, 0, 1]
