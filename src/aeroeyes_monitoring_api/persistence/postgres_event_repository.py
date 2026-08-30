from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
    IngestedAttentionEvent,
)
from aeroeyes_monitoring_api.event_repository import (
    EventAcceptance,
    EventAcceptanceStatus,
    _resolve_existing_event,
)
from aeroeyes_monitoring_api.persistence.models import AttentionEventRecord


class PostgresEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve_existing(
        self,
        candidate: IngestedAttentionEvent,
    ) -> EventAcceptance | None:
        record = self._session.scalar(
            select(AttentionEventRecord).where(
                AttentionEventRecord.event_id == candidate.event_id
            )
        )
        if record is None:
            return None

        return _resolve_existing_event(_record_to_domain(record), candidate)

    def accept(self, candidate: IngestedAttentionEvent) -> EventAcceptance:
        statement = (
            insert(AttentionEventRecord)
            .values(
                event_id=candidate.event_id,
                session_id=candidate.session_id,
                occurred_at=candidate.occurred_at,
                received_at=candidate.received_at,
                state=candidate.state.value,
                severity=candidate.severity.value,
                face_detected=candidate.face_detected,
                eye_state=(
                    candidate.eye_state.value
                    if candidate.eye_state is not None
                    else None
                ),
                closed_duration_ms=candidate.closed_duration_ms,
                schema_version=candidate.schema_version,
            )
            .on_conflict_do_nothing(
                index_elements=[AttentionEventRecord.event_id]
            )
            .returning(AttentionEventRecord.event_id)
        )

        inserted_event_id = self._session.scalar(statement)
        if inserted_event_id is not None:
            return EventAcceptance(
                EventAcceptanceStatus.CREATED,
                candidate,
            )

        existing = self._session.scalar(
            select(AttentionEventRecord).where(
                AttentionEventRecord.event_id == candidate.event_id
            )
        )
        if existing is None:
            raise RuntimeError(
                "conflicting event row was not visible after arbitration"
            )

        return _resolve_existing_event(_record_to_domain(existing), candidate)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("database timestamp must be timezone-aware")

    return value.astimezone(timezone.utc)


def _record_to_domain(record: AttentionEventRecord) -> IngestedAttentionEvent:
    return IngestedAttentionEvent(
        event_id=record.event_id,
        session_id=record.session_id,
        occurred_at=_as_utc(record.occurred_at),
        received_at=_as_utc(record.received_at),
        state=AttentionState(record.state),
        severity=AttentionSeverity(record.severity),
        face_detected=record.face_detected,
        eye_state=EyeState(record.eye_state) if record.eye_state is not None else None,
        closed_duration_ms=record.closed_duration_ms,
        schema_version=record.schema_version,
    )
