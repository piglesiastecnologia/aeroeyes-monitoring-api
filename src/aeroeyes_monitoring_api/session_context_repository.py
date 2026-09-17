from threading import Lock
from typing import Protocol
from uuid import UUID

from aeroeyes_monitoring_api.domain.session_context import SessionContext


class SessionContextRepository(Protocol):
    def get(self, session_id: UUID) -> SessionContext | None: ...

    def save(self, context: SessionContext) -> SessionContext: ...

    def delete(self, session_id: UUID) -> bool: ...


class InMemorySessionContextRepository:
    def __init__(self) -> None:
        self._contexts: dict[UUID, SessionContext] = {}
        self._lock = Lock()

    def get(self, session_id: UUID) -> SessionContext | None:
        with self._lock:
            return self._contexts.get(session_id)

    def save(self, context: SessionContext) -> SessionContext:
        with self._lock:
            self._contexts[context.session_id] = context
            return context

    def delete(self, session_id: UUID) -> bool:
        with self._lock:
            return self._contexts.pop(session_id, None) is not None
