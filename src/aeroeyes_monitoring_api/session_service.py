from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from aeroeyes_monitoring_api.clock import utc_now
from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.session_repository import SessionRepository


class SessionNotFoundError(LookupError):
    """Raised when a requested monitoring session does not exist."""


class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        clock: Callable[[], datetime] = utc_now,
        session_id_factory: Callable[[], UUID] = uuid7,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._session_id_factory = session_id_factory

    def create_session(self) -> MonitoringSession:
        session = MonitoringSession(
            session_id=self._session_id_factory(),
            status=SessionStatus.ACTIVE,
            started_at=self._clock(),
        )
        self._repository.add(session)
        return session

    def get_session(self, session_id: UUID) -> MonitoringSession:
        session = self._repository.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def complete_session(self, session_id: UUID) -> MonitoringSession:
        session = self._repository.complete(session_id, self._clock())
        if session is None:
            raise SessionNotFoundError(session_id)
        return session
