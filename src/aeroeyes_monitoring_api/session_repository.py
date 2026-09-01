from datetime import datetime
from threading import Lock
from typing import Protocol
from uuid import UUID

from aeroeyes_monitoring_api.domain.monitoring_session import MonitoringSession


class DuplicateSessionError(RuntimeError):
    """Raised when a repository already contains a session identity."""


class SessionRepository(Protocol):
    def add(self, session: MonitoringSession) -> None: ...

    def get(self, session_id: UUID) -> MonitoringSession | None: ...

    def complete(
        self,
        session_id: UUID,
        completed_at: datetime,
    ) -> MonitoringSession | None: ...


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[UUID, MonitoringSession] = {}
        self._lock = Lock()

    def add(self, session: MonitoringSession) -> None:
        with self._lock:
            if session.session_id in self._sessions:
                raise DuplicateSessionError(
                    f"session {session.session_id} already exists"
                )
            self._sessions[session.session_id] = session

    def get(self, session_id: UUID) -> MonitoringSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_for_event_ingestion(
        self,
        session_id: UUID,
    ) -> MonitoringSession | None:
        return self.get(session_id)

    def complete(
        self,
        session_id: UUID,
        completed_at: datetime,
    ) -> MonitoringSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

            completed_session = session.complete(completed_at)
            self._sessions[session_id] = completed_session
            return completed_session
