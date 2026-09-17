from collections.abc import Callable
from uuid import UUID

from aeroeyes_monitoring_api.domain.attention_event import IngestedAttentionEvent
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.unit_of_work import UnitOfWork


class SessionAttentionStateService:
    """Read the latest semantic attention transition owned by one session."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get_latest_event(
        self,
        session_id: UUID,
    ) -> IngestedAttentionEvent | None:
        with self._unit_of_work_factory() as uow:
            if uow.sessions.get(session_id) is None:
                raise SessionNotFoundError(session_id)

            return uow.events.latest_for_session(session_id)

    def get_recent_events(
        self,
        session_id: UUID,
        *,
        limit: int,
    ) -> tuple[IngestedAttentionEvent, ...]:
        with self._unit_of_work_factory() as uow:
            if uow.sessions.get(session_id) is None:
                raise SessionNotFoundError(session_id)

            return uow.events.recent_for_session(session_id, limit)
