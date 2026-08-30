from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.persistence.models import MonitoringSessionRecord
from aeroeyes_monitoring_api.session_repository import DuplicateSessionError


class PostgresSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, session: MonitoringSession) -> None:
        statement = (
            insert(MonitoringSessionRecord)
            .values(
                session_id=session.session_id,
                status=session.status.value,
                started_at=session.started_at,
                ended_at=session.ended_at,
            )
            .on_conflict_do_nothing(
                index_elements=[MonitoringSessionRecord.session_id]
            )
            .returning(MonitoringSessionRecord.session_id)
        )

        inserted_session_id = self._session.scalar(statement)
        if inserted_session_id is None:
            raise DuplicateSessionError(
                f"session {session.session_id} already exists"
            )

    def get(self, session_id: UUID) -> MonitoringSession | None:
        record = self._session.scalar(
            select(MonitoringSessionRecord).where(
                MonitoringSessionRecord.session_id == session_id
            )
        )
        if record is None:
            return None
        return _record_to_domain(record)

    def complete(
        self,
        session_id: UUID,
        completed_at: datetime,
    ) -> MonitoringSession | None:
        if (
            completed_at.tzinfo is None
            or completed_at.utcoffset() != timedelta(0)
        ):
            return self._complete_without_update(session_id, completed_at)

        statement = (
            update(MonitoringSessionRecord)
            .where(
                MonitoringSessionRecord.session_id == session_id,
                MonitoringSessionRecord.status == SessionStatus.ACTIVE.value,
                MonitoringSessionRecord.started_at <= completed_at,
            )
            .values(
                status=SessionStatus.COMPLETED.value,
                ended_at=completed_at,
            )
            .returning(
                MonitoringSessionRecord.session_id,
                MonitoringSessionRecord.status,
                MonitoringSessionRecord.started_at,
                MonitoringSessionRecord.ended_at,
            )
        )

        updated = self._session.execute(statement).one_or_none()
        if updated is not None:
            return _row_to_domain(updated)

        return self._complete_without_update(session_id, completed_at)

    def _complete_without_update(
        self,
        session_id: UUID,
        completed_at: datetime,
    ) -> MonitoringSession | None:
        existing = self.get(session_id)
        if existing is None or existing.status is SessionStatus.COMPLETED:
            return existing

        # Keep the domain constructor as the validation boundary for ACTIVE
        # sessions when the conditional update rejects the completion time.
        return existing.complete(completed_at)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("database timestamp must be timezone-aware")

    return value.astimezone(timezone.utc)


def _record_to_domain(record: MonitoringSessionRecord) -> MonitoringSession:
    return MonitoringSession(
        session_id=record.session_id,
        status=SessionStatus(record.status),
        started_at=_as_utc(record.started_at),
        ended_at=_as_utc(record.ended_at) if record.ended_at is not None else None,
    )


def _row_to_domain(
    row: Row[tuple[UUID, str, datetime, datetime | None]],
) -> MonitoringSession:
    return MonitoringSession(
        session_id=row.session_id,
        status=SessionStatus(row.status),
        started_at=_as_utc(row.started_at),
        ended_at=_as_utc(row.ended_at) if row.ended_at is not None else None,
    )
