from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from aeroeyes_monitoring_api.clock import utc_now
from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
    IngestedAttentionEvent,
)
from aeroeyes_monitoring_api.domain.monitoring_session import SessionStatus
from aeroeyes_monitoring_api.event_repository import (
    EventAcceptance,
    EventAcceptanceStatus,
    EventRepository,
)
from aeroeyes_monitoring_api.session_repository import SessionRepository
from aeroeyes_monitoring_api.session_service import SessionNotFoundError


class UnsupportedSchemaVersionError(ValueError):
    """Raised when an event uses an unsupported payload schema version."""


class EventOutsideSessionError(ValueError):
    """Raised when an event occurred outside its session's temporal window."""


class EventConflictError(RuntimeError):
    """Raised when an event identity is already bound to different semantics."""


class EventIngestionService:
    def __init__(
        self,
        session_repository: SessionRepository,
        event_repository: EventRepository,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_repository = session_repository
        self._event_repository = event_repository
        self._clock = clock

    def ingest(
        self,
        session_id: UUID,
        *,
        event_id: UUID,
        occurred_at: datetime,
        state: AttentionState,
        severity: AttentionSeverity,
        face_detected: bool,
        eye_state: EyeState | None,
        closed_duration_ms: int | None,
        schema_version: int,
    ) -> EventAcceptance:
        if type(schema_version) is not int or schema_version != 1:
            raise UnsupportedSchemaVersionError(schema_version)

        session = self._session_repository.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        candidate = IngestedAttentionEvent(
            event_id=event_id,
            session_id=session_id,
            occurred_at=occurred_at,
            received_at=self._clock(),
            state=state,
            severity=severity,
            face_detected=face_detected,
            eye_state=eye_state,
            closed_duration_ms=closed_duration_ms,
            schema_version=schema_version,
        )

        existing = self._event_repository.resolve_existing(candidate)
        if (
            existing is not None
            and existing.status is EventAcceptanceStatus.ALREADY_PROCESSED
        ):
            return existing

        if occurred_at < session.started_at:
            raise EventOutsideSessionError(session_id)
        if (
            session.status is SessionStatus.COMPLETED
            and session.ended_at is not None
            and occurred_at > session.ended_at
        ):
            raise EventOutsideSessionError(session_id)

        result = self._event_repository.accept(candidate)

        if result.status is EventAcceptanceStatus.CONFLICT:
            raise EventConflictError(event_id)

        return result
