"""Add session context persistence.

Revision ID: 002_session_context
Revises: 001_monitoring_core
Create Date: 2026-09-01

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_session_context"
down_revision: str | None = "001_monitoring_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_contexts",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("flight_number", sa.Text(), nullable=True),
        sa.Column("departure_icao", sa.Text(), nullable=True),
        sa.Column("destination_icao", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["monitoring_sessions.session_id"],
            name="fk_session_contexts_session_id_monitoring_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "session_id",
            name="pk_session_contexts",
        ),
    )


def downgrade() -> None:
    op.drop_table("session_contexts")
