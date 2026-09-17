from datetime import datetime, timezone
from uuid import UUID

import pytest

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
    IngestedAttentionEvent,
)
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.session_attention_state_service import (
    SessionAttentionStateService,
)
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork


SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000010")
OCCURRED_AT = datetime(2026, 9, 11, 23, 17, tzinfo=timezone.utc)


def build_service(
    *,
    include_session: bool = True,
    include_event: bool = False,
) -> SessionAttentionStateService:
    sessions = InMemorySessionRepository()
    events = InMemoryEventRepository()
    contexts = InMemorySessionContextRepository()
    if include_session:
        sessions.add(
            MonitoringSession(
                session_id=SESSION_ID,
                status=SessionStatus.ACTIVE,
                started_at=OCCURRED_AT,
            )
        )
    if include_event:
        events.accept(
            IngestedAttentionEvent(
                event_id=EVENT_ID,
                session_id=SESSION_ID,
                occurred_at=OCCURRED_AT,
                received_at=OCCURRED_AT,
                state=AttentionState.NORMAL,
                severity=AttentionSeverity.INFO,
                face_detected=True,
                eye_state=EyeState.OPEN,
                closed_duration_ms=0,
                schema_version=1,
            )
        )
    return SessionAttentionStateService(
        lambda: InMemoryUnitOfWork(sessions, events, contexts)
    )


def test_existing_session_without_events_returns_none() -> None:
    assert build_service().get_latest_event(SESSION_ID) is None


def test_existing_session_returns_latest_event() -> None:
    result = build_service(include_event=True).get_latest_event(SESSION_ID)

    assert result is not None
    assert result.event_id == EVENT_ID


def test_existing_session_returns_recent_events() -> None:
    result = build_service(include_event=True).get_recent_events(
        SESSION_ID,
        limit=10,
    )

    assert tuple(event.event_id for event in result) == (EVENT_ID,)


def test_unknown_session_is_rejected_before_event_read() -> None:
    with pytest.raises(SessionNotFoundError):
        build_service(include_session=False).get_latest_event(SESSION_ID)
