from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
)
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.event_ingestion_service import EventIngestionService
from aeroeyes_monitoring_api.event_repository import EventAcceptanceStatus
from aeroeyes_monitoring_api.persistence.database import create_session_factory
from aeroeyes_monitoring_api.persistence.models import AttentionEventRecord
from aeroeyes_monitoring_api.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)
from aeroeyes_monitoring_api.persistence.postgres_unit_of_work import (
    PostgresUnitOfWork,
)

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000010")
STARTED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
COMPLETED_AT = STARTED_AT + timedelta(minutes=30)
FIRST_RECEIVED_AT = STARTED_AT + timedelta(hours=2)


def seed_active_session(engine: Engine) -> None:
    with Session(engine) as database_session, database_session.begin():
        PostgresSessionRepository(database_session).add(
            MonitoringSession(
                session_id=SESSION_ID,
                status=SessionStatus.ACTIVE,
                started_at=STARTED_AT,
            )
        )


def service_for(
    engine: Engine,
    clock_times: tuple[datetime, ...],
) -> EventIngestionService:
    times = iter(clock_times)
    session_factory = create_session_factory(engine)
    return EventIngestionService(
        lambda: PostgresUnitOfWork(session_factory),
        clock=lambda: next(times),
    )


def ingest(
    service: EventIngestionService,
    *,
    occurred_at: datetime = STARTED_AT + timedelta(minutes=10),
):
    return service.ingest(
        SESSION_ID,
        event_id=EVENT_ID,
        occurred_at=occurred_at,
        state=AttentionState.ATTENTION,
        severity=AttentionSeverity.MEDIUM,
        face_detected=True,
        eye_state=EyeState.CLOSED,
        closed_duration_ms=1250,
        schema_version=1,
    )


def test_service_persists_new_event_and_replays_original(
    postgres_engine: Engine,
) -> None:
    seed_active_session(postgres_engine)
    service = service_for(
        postgres_engine,
        (FIRST_RECEIVED_AT, FIRST_RECEIVED_AT + timedelta(minutes=1)),
    )

    created = ingest(service)
    replay = ingest(service)

    assert created.status is EventAcceptanceStatus.CREATED
    assert replay.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert replay.event == created.event
    assert replay.event.received_at == FIRST_RECEIVED_AT
    with Session(postgres_engine) as verification:
        assert verification.scalar(
            select(func.count()).select_from(AttentionEventRecord)
        ) == 1


def test_replay_bypasses_completed_session_window_validation(
    postgres_engine: Engine,
) -> None:
    seed_active_session(postgres_engine)
    occurred_after_later_completion = COMPLETED_AT + timedelta(minutes=30)
    service = service_for(
        postgres_engine,
        (FIRST_RECEIVED_AT, FIRST_RECEIVED_AT + timedelta(minutes=1)),
    )

    created = ingest(service, occurred_at=occurred_after_later_completion)
    with Session(postgres_engine) as database_session:
        completed = PostgresSessionRepository(database_session).complete(
            SESSION_ID,
            COMPLETED_AT,
        )
        database_session.commit()

    replay = ingest(service, occurred_at=occurred_after_later_completion)

    assert completed is not None
    assert created.status is EventAcceptanceStatus.CREATED
    assert replay.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert replay.event == created.event
    assert replay.event.received_at == FIRST_RECEIVED_AT
