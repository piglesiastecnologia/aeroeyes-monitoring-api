from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from aeroeyes_monitoring_api.clock import utc_now
from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.unit_of_work import UnitOfWork


class SessionNotFoundError(LookupError):
    """Raised when a requested monitoring session does not exist."""


class SessionService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: Callable[[], datetime] = utc_now,
        session_id_factory: Callable[[], UUID] = uuid7,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._session_id_factory = session_id_factory

    def create_session(self) -> MonitoringSession:
        session = MonitoringSession(
            session_id=self._session_id_factory(),
            status=SessionStatus.ACTIVE,
            started_at=self._clock(),
        )
        with self._unit_of_work_factory() as uow:
            uow.sessions.add(session)
            uow.commit()
        return session

    def get_session(self, session_id: UUID) -> MonitoringSession:
        with self._unit_of_work_factory() as uow:
            session = uow.sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(session_id)
            return session

    def complete_session(self, session_id: UUID) -> MonitoringSession:
        with self._unit_of_work_factory() as uow:
            session = uow.sessions.complete(session_id, self._clock())
            if session is None:
                raise SessionNotFoundError(session_id)
            uow.commit()
            return session
