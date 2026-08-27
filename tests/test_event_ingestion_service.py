from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
)
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.event_ingestion_service import (
    EventConflictError,
    EventIngestionService,
    EventOutsideSessionError,
    UnsupportedSchemaVersionError,
)
from aeroeyes_monitoring_api.event_repository import (
    EventAcceptanceStatus,
    InMemoryEventRepository,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import SessionNotFoundError

EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000010")
SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
OTHER_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000002")
STARTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
ENDED_AT = STARTED_AT + timedelta(minutes=30)
RECEIVED_AT = STARTED_AT + timedelta(hours=2)


def session(
    *,
    session_id: UUID = SESSION_ID,
    status: SessionStatus = SessionStatus.ACTIVE,
) -> MonitoringSession:
    return MonitoringSession(
        session_id=session_id,
        status=status,
        started_at=STARTED_AT,
        ended_at=ENDED_AT if status is SessionStatus.COMPLETED else None,
    )


def service_for(
    monitoring_session: MonitoringSession | None,
    *,
    clock_time: datetime = RECEIVED_AT,
) -> tuple[EventIngestionService, InMemorySessionRepository]:
    sessions = InMemorySessionRepository()
    if monitoring_session is not None:
        sessions.add(monitoring_session)
    service = EventIngestionService(
        sessions,
        InMemoryEventRepository(),
        clock=lambda: clock_time,
    )
    return service, sessions


def ingest(
    service: EventIngestionService,
    *,
    session_id: UUID = SESSION_ID,
    occurred_at: datetime = STARTED_AT,
    event_id: UUID = EVENT_ID,
    state: AttentionState = AttentionState.NORMAL,
    schema_version: int = 1,
):
    return service.ingest(
        session_id,
        event_id=event_id,
        occurred_at=occurred_at,
        state=state,
        severity=AttentionSeverity.LOW,
        face_detected=True,
        eye_state=EyeState.OPEN,
        closed_duration_ms=0,
        schema_version=schema_version,
    )


def test_unsupported_schema_version_precedes_session_lookup() -> None:
    service, _ = service_for(None)

    with pytest.raises(UnsupportedSchemaVersionError):
        ingest(service, schema_version=2)


def test_unknown_session_is_rejected() -> None:
    service, _ = service_for(None)

    with pytest.raises(SessionNotFoundError):
        ingest(service)


@pytest.mark.parametrize("occurred_at", [STARTED_AT, STARTED_AT + timedelta(minutes=1)])
def test_active_session_accepts_event_at_or_after_start(
    occurred_at: datetime,
) -> None:
    service, _ = service_for(session())

    result = ingest(service, occurred_at=occurred_at)

    assert result.status is EventAcceptanceStatus.CREATED


def test_active_session_rejects_event_before_start() -> None:
    service, _ = service_for(session())

    with pytest.raises(EventOutsideSessionError):
        ingest(service, occurred_at=STARTED_AT - timedelta(microseconds=1))


def test_active_session_accepts_future_producer_timestamp() -> None:
    service, _ = service_for(session(), clock_time=RECEIVED_AT)

    result = ingest(service, occurred_at=RECEIVED_AT + timedelta(hours=1))

    assert result.status is EventAcceptanceStatus.CREATED


@pytest.mark.parametrize("occurred_at", [STARTED_AT, ENDED_AT])
def test_completed_session_accepts_inclusive_boundaries(
    occurred_at: datetime,
) -> None:
    service, _ = service_for(session(status=SessionStatus.COMPLETED))

    result = ingest(service, occurred_at=occurred_at)

    assert result.status is EventAcceptanceStatus.CREATED


def test_completed_session_accepts_valid_late_arrival() -> None:
    service, _ = service_for(
        session(status=SessionStatus.COMPLETED),
        clock_time=ENDED_AT + timedelta(hours=2),
    )

    result = ingest(service, occurred_at=STARTED_AT + timedelta(minutes=15))

    assert result.status is EventAcceptanceStatus.CREATED
    assert result.event.received_at > ENDED_AT


@pytest.mark.parametrize(
    "occurred_at",
    [STARTED_AT - timedelta(microseconds=1), ENDED_AT + timedelta(microseconds=1)],
)
def test_completed_session_rejects_event_outside_window(
    occurred_at: datetime,
) -> None:
    service, _ = service_for(session(status=SessionStatus.COMPLETED))

    with pytest.raises(EventOutsideSessionError):
        ingest(service, occurred_at=occurred_at)


def test_injected_clock_determines_received_at() -> None:
    service, _ = service_for(session(), clock_time=RECEIVED_AT)

    result = ingest(service)

    assert result.event.received_at == RECEIVED_AT


def test_replay_returns_already_processed_with_original_received_at() -> None:
    times = iter((RECEIVED_AT, RECEIVED_AT + timedelta(minutes=1)))
    sessions = InMemorySessionRepository()
    sessions.add(session())
    service = EventIngestionService(
        sessions,
        InMemoryEventRepository(),
        clock=lambda: next(times),
    )

    created = ingest(service)
    replay = ingest(service)

    assert created.status is EventAcceptanceStatus.CREATED
    assert replay.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert replay.event is created.event
    assert replay.event.received_at == RECEIVED_AT


def test_replay_remains_processed_after_session_completes_before_event_time() -> None:
    first_received_at = STARTED_AT + timedelta(minutes=5)
    replay_received_at = ENDED_AT + timedelta(minutes=5)
    future_occurred_at = ENDED_AT + timedelta(minutes=30)

    times = iter((first_received_at, replay_received_at))
    sessions = InMemorySessionRepository()
    sessions.add(session())
    service = EventIngestionService(
        sessions,
        InMemoryEventRepository(),
        clock=lambda: next(times),
    )

    created = ingest(
        service,
        occurred_at=future_occurred_at,
    )

    completed = sessions.complete(
        SESSION_ID,
        ENDED_AT,
    )

    replay = ingest(
        service,
        occurred_at=future_occurred_at,
    )

    assert completed is not None
    assert created.status is EventAcceptanceStatus.CREATED
    assert replay.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert replay.event is created.event
    assert replay.event.received_at == first_received_at


def test_repository_conflict_becomes_application_conflict() -> None:
    service, _ = service_for(session())
    ingest(service)

    with pytest.raises(EventConflictError):
        ingest(service, state=AttentionState.CRITICAL)


def test_existing_other_session_with_same_event_id_conflicts() -> None:
    service, sessions = service_for(session())
    sessions.add(session(session_id=OTHER_SESSION_ID))
    ingest(service)

    with pytest.raises(EventConflictError):
        ingest(service, session_id=OTHER_SESSION_ID)


def test_temporal_validation_precedes_event_id_conflict() -> None:
    service, sessions = service_for(session())
    sessions.add(
        MonitoringSession(
            session_id=OTHER_SESSION_ID,
            status=SessionStatus.ACTIVE,
            started_at=STARTED_AT + timedelta(minutes=10),
        )
    )
    ingest(service)

    with pytest.raises(EventOutsideSessionError):
        ingest(service, session_id=OTHER_SESSION_ID, occurred_at=STARTED_AT)
