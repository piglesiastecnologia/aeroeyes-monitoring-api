from collections.abc import Callable
from uuid import UUID

from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.unit_of_work import UnitOfWork


class SessionContextNotFoundError(LookupError):
    """Raised when a monitoring session exists but has no SessionContext."""


class SessionContextService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get_context(self, session_id: UUID) -> SessionContext:
        with self._unit_of_work_factory() as uow:
            if uow.sessions.get(session_id) is None:
                raise SessionNotFoundError(session_id)

            context = uow.contexts.get(session_id)
            if context is None:
                raise SessionContextNotFoundError(session_id)
            return context

    def replace_context(
        self,
        session_id: UUID,
        *,
        flight_number: str | None = None,
        departure_icao: str | None = None,
        destination_icao: str | None = None,
    ) -> SessionContext:
        candidate = SessionContext(
            session_id=session_id,
            flight_number=flight_number,
            departure_icao=departure_icao,
            destination_icao=destination_icao,
        )

        with self._unit_of_work_factory() as uow:
            if uow.sessions.get(session_id) is None:
                raise SessionNotFoundError(session_id)

            persisted = uow.contexts.save(candidate)
            uow.commit()
            return persisted

    def delete_context(self, session_id: UUID) -> bool:
        with self._unit_of_work_factory() as uow:
            if uow.sessions.get(session_id) is None:
                raise SessionNotFoundError(session_id)

            deleted = uow.contexts.delete(session_id)
            if deleted:
                uow.commit()
            return deleted
