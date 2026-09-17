from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from aeroeyes_monitoring_api.persistence.database import Base


class MonitoringSessionRecord(Base):
    __tablename__ = "monitoring_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED')",
            name="status_values",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status = 'COMPLETED' AND ended_at IS NOT NULL)",
            name="status_ended_at",
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ended_at_chronology",
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class SessionContextRecord(Base):
    __tablename__ = "session_contexts"

    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "monitoring_sessions.session_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
        nullable=False,
    )
    flight_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    departure_icao: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_icao: Mapped[str | None] = mapped_column(Text, nullable=True)


class AttentionEventRecord(Base):
    __tablename__ = "attention_events"
    __table_args__ = (
        CheckConstraint(
            "state IN ('NORMAL', 'ATTENTION', 'CRITICAL', 'NO_FACE')",
            name="state_values",
        ),
        CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH')",
            name="severity_values",
        ),
        CheckConstraint(
            "eye_state IS NULL OR "
            "eye_state IN ('OPEN', 'CLOSED', 'PROLONGED_CLOSURE')",
            name="eye_state_values",
        ),
        CheckConstraint(
            "closed_duration_ms IS NULL OR closed_duration_ms >= 0",
            name="closed_duration_non_negative",
        ),
        CheckConstraint(
            "schema_version = 1",
            name="schema_version_supported",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "monitoring_sessions.session_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    face_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    eye_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
