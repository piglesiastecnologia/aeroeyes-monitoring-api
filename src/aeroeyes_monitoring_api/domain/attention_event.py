from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID


class AttentionState(StrEnum):
    NORMAL = "NORMAL"
    ATTENTION = "ATTENTION"
    CRITICAL = "CRITICAL"
    NO_FACE = "NO_FACE"


class AttentionSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EyeState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PROLONGED_CLOSURE = "PROLONGED_CLOSURE"


SemanticPayload = tuple[
    datetime,
    AttentionState,
    AttentionSeverity,
    bool,
    EyeState | None,
    int | None,
    int,
]


def _require_uuid7(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID) or value.version != 7:
        raise ValueError(f"{field_name} must be a UUIDv7")


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class IngestedAttentionEvent:
    event_id: UUID
    session_id: UUID
    occurred_at: datetime
    received_at: datetime
    state: AttentionState
    severity: AttentionSeverity
    face_detected: bool
    eye_state: EyeState | None
    closed_duration_ms: int | None
    schema_version: int

    def __post_init__(self) -> None:
        _require_uuid7(self.event_id, "event_id")
        _require_uuid7(self.session_id, "session_id")
        _require_utc(self.occurred_at, "occurred_at")
        _require_utc(self.received_at, "received_at")

        if not isinstance(self.state, AttentionState):
            raise ValueError("state must be an AttentionState")
        if not isinstance(self.severity, AttentionSeverity):
            raise ValueError("severity must be an AttentionSeverity")
        if type(self.face_detected) is not bool:
            raise ValueError("face_detected must be a boolean")
        if self.eye_state is not None and not isinstance(self.eye_state, EyeState):
            raise ValueError("eye_state must be an EyeState or None")
        if self.closed_duration_ms is not None:
            if type(self.closed_duration_ms) is not int:
                raise ValueError("closed_duration_ms must be an integer or None")
            if self.closed_duration_ms < 0:
                raise ValueError("closed_duration_ms cannot be negative")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("schema_version must be the supported integer version 1")

    @property
    def semantic_payload(self) -> SemanticPayload:
        return (
            self.occurred_at,
            self.state,
            self.severity,
            self.face_detected,
            self.eye_state,
            self.closed_duration_ms,
            self.schema_version,
        )
