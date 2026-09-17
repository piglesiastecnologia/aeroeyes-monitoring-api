from uuid import UUID

from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")


def test_contexts_is_the_shared_repository() -> None:
    sessions = InMemorySessionRepository()
    events = InMemoryEventRepository()
    contexts = InMemorySessionContextRepository()

    with InMemoryUnitOfWork(sessions, events, contexts) as uow:
        assert uow.contexts is contexts


def test_context_state_survives_across_unit_of_work_instances() -> None:
    sessions = InMemorySessionRepository()
    events = InMemoryEventRepository()
    contexts = InMemorySessionContextRepository()
    unit_of_work_factory = lambda: InMemoryUnitOfWork(sessions, events, contexts)
    expected = SessionContext(
        session_id=SESSION_ID,
        flight_number="AZUL 1234",
        departure_icao="SBGR",
        destination_icao="SBRJ",
    )

    with unit_of_work_factory() as first:
        first.contexts.save(expected)
        first.commit()

    with unit_of_work_factory() as second:
        assert second.contexts is contexts
        assert second.contexts.get(SESSION_ID) == expected
