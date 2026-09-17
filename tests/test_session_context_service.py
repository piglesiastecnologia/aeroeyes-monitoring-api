from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)
from aeroeyes_monitoring_api.session_context_service import (
    SessionContextNotFoundError,
    SessionContextService,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
MISSING_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000099")
STARTED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def monitoring_session(
    status: SessionStatus = SessionStatus.ACTIVE,
) -> MonitoringSession:
    return MonitoringSession(
        session_id=SESSION_ID,
        status=status,
        started_at=STARTED_AT,
        ended_at=(
            STARTED_AT + timedelta(minutes=30)
            if status is SessionStatus.COMPLETED
            else None
        ),
    )


def context() -> SessionContext:
    return SessionContext(
        session_id=SESSION_ID,
        flight_number="LA8084",
        departure_icao="SBGR",
        destination_icao="SBGL",
    )


class RecordingContextRepository(InMemorySessionContextRepository):
    def __init__(self) -> None:
        super().__init__()
        self.save_calls: list[SessionContext] = []
        self.delete_calls: list[UUID] = []

    def save(self, candidate: SessionContext) -> SessionContext:
        self.save_calls.append(candidate)
        return super().save(candidate)

    def delete(self, session_id: UUID) -> bool:
        self.delete_calls.append(session_id)
        return super().delete(session_id)


class RecordingUnitOfWork(InMemoryUnitOfWork):
    def __init__(
        self,
        sessions: InMemorySessionRepository,
        contexts: RecordingContextRepository,
    ) -> None:
        super().__init__(sessions, InMemoryEventRepository(), contexts)
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


def service_fixture(
    *,
    session: MonitoringSession | None = None,
    existing_context: SessionContext | None = None,
) -> tuple[
    SessionContextService,
    RecordingContextRepository,
    list[RecordingUnitOfWork],
]:
    sessions = InMemorySessionRepository()
    contexts = RecordingContextRepository()
    if session is not None:
        sessions.add(session)
    if existing_context is not None:
        contexts.save(existing_context)
        contexts.save_calls.clear()

    created_uows: list[RecordingUnitOfWork] = []

    def unit_of_work_factory() -> RecordingUnitOfWork:
        uow = RecordingUnitOfWork(sessions, contexts)
        created_uows.append(uow)
        return uow

    return SessionContextService(unit_of_work_factory), contexts, created_uows


def test_get_existing_context_returns_it_without_commit() -> None:
    expected = context()
    service, _, uows = service_fixture(
        session=monitoring_session(),
        existing_context=expected,
    )

    assert service.get_context(SESSION_ID) == expected
    assert [uow.commit_count for uow in uows] == [0]


def test_get_missing_session_raises_session_not_found() -> None:
    service, _, uows = service_fixture()

    with pytest.raises(SessionNotFoundError):
        service.get_context(MISSING_SESSION_ID)

    assert [uow.commit_count for uow in uows] == [0]


def test_get_missing_context_raises_context_not_found() -> None:
    service, _, uows = service_fixture(session=monitoring_session())

    with pytest.raises(SessionContextNotFoundError):
        service.get_context(SESSION_ID)

    assert [uow.commit_count for uow in uows] == [0]


def test_replace_creates_context_and_commits_once() -> None:
    service, contexts, uows = service_fixture(session=monitoring_session())

    replaced = service.replace_context(SESSION_ID, flight_number="LA8084")

    assert contexts.get(SESSION_ID) == replaced
    assert contexts.save_calls == [replaced]
    assert [uow.commit_count for uow in uows] == [1]


def test_replace_existing_context_is_complete_replacement_and_clears_omitted_fields() -> None:
    service, contexts, _ = service_fixture(
        session=monitoring_session(),
        existing_context=context(),
    )

    replaced = service.replace_context(SESSION_ID, departure_icao="SBSP")

    assert replaced == SessionContext(
        session_id=SESSION_ID,
        flight_number=None,
        departure_icao="SBSP",
        destination_icao=None,
    )
    assert contexts.get(SESSION_ID) == replaced


def test_replace_explicit_none_clears_all_old_fields() -> None:
    service, contexts, _ = service_fixture(
        session=monitoring_session(),
        existing_context=context(),
    )

    replaced = service.replace_context(
        SESSION_ID,
        flight_number=None,
        departure_icao=None,
        destination_icao=None,
    )

    assert replaced == SessionContext(session_id=SESSION_ID)
    assert contexts.get(SESSION_ID) == replaced


def test_replace_missing_session_does_not_save_or_commit() -> None:
    service, contexts, uows = service_fixture()

    with pytest.raises(SessionNotFoundError):
        service.replace_context(MISSING_SESSION_ID, departure_icao="SBSP")

    assert contexts.save_calls == []
    assert [uow.commit_count for uow in uows] == [0]


def test_invalid_icao_is_rejected_before_opening_unit_of_work() -> None:
    service, contexts, uows = service_fixture(session=monitoring_session())

    with pytest.raises(ValueError, match="departure_icao"):
        service.replace_context(SESSION_ID, departure_icao="GRU")

    assert contexts.save_calls == []
    assert uows == []


def test_replace_uses_session_context_domain_normalization() -> None:
    service, _, _ = service_fixture(session=monitoring_session())

    replaced = service.replace_context(
        SESSION_ID,
        flight_number="  la8084 ",
        departure_icao=" sbgr ",
        destination_icao="  ",
    )

    assert replaced == SessionContext(
        session_id=SESSION_ID,
        flight_number="LA8084",
        departure_icao="SBGR",
        destination_icao=None,
    )


def test_completed_session_context_can_be_replaced() -> None:
    service, _, uows = service_fixture(session=monitoring_session(SessionStatus.COMPLETED))

    replaced = service.replace_context(SESSION_ID, destination_icao="SBRJ")

    assert replaced.destination_icao == "SBRJ"
    assert [uow.commit_count for uow in uows] == [1]


def test_delete_existing_context_returns_true_and_commits_once() -> None:
    service, contexts, uows = service_fixture(
        session=monitoring_session(),
        existing_context=context(),
    )

    assert service.delete_context(SESSION_ID) is True
    assert contexts.get(SESSION_ID) is None
    assert contexts.delete_calls == [SESSION_ID]
    assert [uow.commit_count for uow in uows] == [1]


def test_delete_missing_context_returns_false_without_commit() -> None:
    service, contexts, uows = service_fixture(session=monitoring_session())

    assert service.delete_context(SESSION_ID) is False
    assert contexts.delete_calls == [SESSION_ID]
    assert [uow.commit_count for uow in uows] == [0]


def test_delete_missing_session_does_not_delete_or_commit() -> None:
    service, contexts, uows = service_fixture()

    with pytest.raises(SessionNotFoundError):
        service.delete_context(MISSING_SESSION_ID)

    assert contexts.delete_calls == []
    assert [uow.commit_count for uow in uows] == [0]


def test_completed_session_context_can_be_deleted() -> None:
    service, _, uows = service_fixture(
        session=monitoring_session(SessionStatus.COMPLETED),
        existing_context=context(),
    )

    assert service.delete_context(SESSION_ID) is True
    assert [uow.commit_count for uow in uows] == [1]


def test_each_operation_uses_a_fresh_unit_of_work() -> None:
    service, _, uows = service_fixture(
        session=monitoring_session(),
        existing_context=context(),
    )

    service.get_context(SESSION_ID)
    service.replace_context(SESSION_ID, flight_number="LA8084")
    service.delete_context(SESSION_ID)

    assert len(uows) == 3
    assert len({id(uow) for uow in uows}) == 3
    assert [uow.commit_count for uow in uows] == [0, 1, 1]
