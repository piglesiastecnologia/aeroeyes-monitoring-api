from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.persistence.postgres_event_repository import (
    PostgresEventRepository,
)
from aeroeyes_monitoring_api.persistence.postgres_session_context_repository import (
    PostgresSessionContextRepository,
)
from aeroeyes_monitoring_api.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)


class PostgresUnitOfWork:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._sessions: PostgresSessionRepository | None = None
        self._events: PostgresEventRepository | None = None
        self._contexts: PostgresSessionContextRepository | None = None

    @property
    def sessions(self) -> PostgresSessionRepository:
        if self._sessions is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._sessions

    @property
    def events(self) -> PostgresEventRepository:
        if self._events is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._events

    @property
    def contexts(self) -> PostgresSessionContextRepository:
        if self._contexts is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._contexts

    def __enter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("UnitOfWork is already active")

        session = self._session_factory()
        self._session = session
        self._sessions = PostgresSessionRepository(session)
        self._events = PostgresEventRepository(session)
        self._contexts = PostgresSessionContextRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if session.in_transaction():
                session.rollback()
        finally:
            try:
                session.close()
            finally:
                self._session = None
                self._sessions = None
                self._events = None
                self._contexts = None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._session
