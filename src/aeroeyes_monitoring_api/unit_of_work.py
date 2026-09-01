from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from aeroeyes_monitoring_api.domain.monitoring_session import MonitoringSession
from aeroeyes_monitoring_api.event_repository import (
    EventRepository,
    InMemoryEventRepository,
)
from aeroeyes_monitoring_api.session_repository import (
    InMemorySessionRepository,
    SessionRepository,
)


class EventIngestionSessionRepository(SessionRepository, Protocol):
    def get_for_event_ingestion(
        self,
        session_id: UUID,
    ) -> MonitoringSession | None: ...


class UnitOfWork(Protocol):
    sessions: EventIngestionSessionRepository
    events: EventRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class InMemoryUnitOfWork:
    def __init__(
        self,
        sessions: InMemorySessionRepository,
        events: InMemoryEventRepository,
    ) -> None:
        self.sessions = sessions
        self.events = events

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.rollback()

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass
