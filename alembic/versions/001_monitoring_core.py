"""Initial monitoring persistence.

Revision ID: 001_monitoring_core
Revises:
Create Date: 2026-08-29

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_monitoring_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitoring_sessions",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED')",
            name=op.f("ck_monitoring_sessions_status_values"),
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND ended_at IS NULL) OR "
            "(status = 'COMPLETED' AND ended_at IS NOT NULL)",
            name=op.f("ck_monitoring_sessions_status_ended_at"),
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_monitoring_sessions_ended_at_chronology"),
        ),
        sa.PrimaryKeyConstraint(
            "session_id",
            name="pk_monitoring_sessions",
        ),
    )

    op.create_table(
        "attention_events",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("face_detected", sa.Boolean(), nullable=False),
        sa.Column("eye_state", sa.Text(), nullable=True),
        sa.Column("closed_duration_ms", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "state IN ('NORMAL', 'ATTENTION', 'CRITICAL', 'NO_FACE')",
            name=op.f("ck_attention_events_state_values"),
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH')",
            name=op.f("ck_attention_events_severity_values"),
        ),
        sa.CheckConstraint(
            "eye_state IS NULL OR "
            "eye_state IN ('OPEN', 'CLOSED', 'PROLONGED_CLOSURE')",
            name=op.f("ck_attention_events_eye_state_values"),
        ),
        sa.CheckConstraint(
            "closed_duration_ms IS NULL OR closed_duration_ms >= 0",
            name=op.f("ck_attention_events_closed_duration_non_negative"),
        ),
        sa.CheckConstraint(
            "schema_version = 1",
            name=op.f("ck_attention_events_schema_version_supported"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["monitoring_sessions.session_id"],
            name="fk_attention_events_session_id_monitoring_sessions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "event_id",
            name="pk_attention_events",
        ),
    )


def downgrade() -> None:
    op.drop_table("attention_events")
    op.drop_table("monitoring_sessions")
