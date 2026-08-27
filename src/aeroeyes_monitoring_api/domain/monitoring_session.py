from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID


class SessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class MonitoringSession:
    session_id: UUID
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, UUID) or self.session_id.version != 7:
            raise ValueError("session_id must be a UUIDv7")
        if not isinstance(self.status, SessionStatus):
            raise ValueError("status must be a SessionStatus")

        _require_utc(self.started_at, "started_at")

        if self.status is SessionStatus.ACTIVE and self.ended_at is not None:
            raise ValueError("an ACTIVE session cannot have ended_at")
        if self.status is SessionStatus.COMPLETED and self.ended_at is None:
            raise ValueError("a COMPLETED session must have ended_at")

        if self.ended_at is not None:
            _require_utc(self.ended_at, "ended_at")
            if self.ended_at < self.started_at:
                raise ValueError("ended_at cannot be earlier than started_at")

    def complete(self, completed_at: datetime) -> "MonitoringSession":
        if self.status is SessionStatus.COMPLETED:
            return self

        return replace(
            self,
            status=SessionStatus.COMPLETED,
            ended_at=completed_at,
        )
