from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
    IngestedAttentionEvent,
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
    EventAcceptance,
    EventAcceptanceStatus,
    InMemoryEventRepository,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork

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
    events = InMemoryEventRepository()
    service = EventIngestionService(
        lambda: InMemoryUnitOfWork(sessions, events),
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


def stored_event(*, received_at: datetime = RECEIVED_AT) -> IngestedAttentionEvent:
    return IngestedAttentionEvent(
        event_id=EVENT_ID,
        session_id=SESSION_ID,
        occurred_at=STARTED_AT,
        received_at=received_at,
        state=AttentionState.NORMAL,
        severity=AttentionSeverity.LOW,
        face_detected=True,
        eye_state=EyeState.OPEN,
        closed_duration_ms=0,
        schema_version=1,
    )


class RecordingSessions:
    def __init__(
        self,
        calls: list[str],
        result: MonitoringSession | None,
    ) -> None:
        self._calls = calls
        self._result = result

    def get_for_event_ingestion(
        self,
        session_id: UUID,
    ) -> MonitoringSession | None:
        self._calls.append("get_for_event_ingestion")
        return self._result


class RecordingEvents:
    def __init__(
        self,
        calls: list[str],
        *,
        resolved: EventAcceptance | None = None,
        accepted: EventAcceptance | None = None,
    ) -> None:
        self._calls = calls
        self._resolved = resolved
        self._accepted = accepted

    def resolve_existing(
        self,
        candidate: IngestedAttentionEvent,
    ) -> EventAcceptance | None:
        self._calls.append("resolve_existing")
        return self._resolved

    def accept(self, candidate: IngestedAttentionEvent) -> EventAcceptance:
        self._calls.append("accept")
        if self._accepted is not None:
            return self._accepted
        return EventAcceptance(EventAcceptanceStatus.CREATED, candidate)


class RecordingUnitOfWork:
    def __init__(
        self,
        calls: list[str],
        sessions: RecordingSessions,
        events: RecordingEvents,
    ) -> None:
        self._calls = calls
        self.sessions = sessions
        self.events = events

    def __enter__(self):
        self._calls.append("enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._calls.append("exit")

    def commit(self) -> None:
        self._calls.append("commit")

    def rollback(self) -> None:
        self._calls.append("rollback")


def recording_service(
    monitoring_session: MonitoringSession | None,
    *,
    resolved: EventAcceptance | None = None,
    accepted: EventAcceptance | None = None,
    clock_time: datetime = RECEIVED_AT + timedelta(minutes=1),
) -> tuple[EventIngestionService, list[str]]:
    calls: list[str] = []
    uow = RecordingUnitOfWork(
        calls,
        RecordingSessions(calls, monitoring_session),
        RecordingEvents(calls, resolved=resolved, accepted=accepted),
    )
    return (
        EventIngestionService(lambda: uow, clock=lambda: clock_time),
        calls,
    )


def test_unsupported_schema_version_precedes_entering_unit_of_work() -> None:
    factory_called = False

    def unit_of_work_factory():
        nonlocal factory_called
        factory_called = True
        raise AssertionError("unsupported schema must not construct a UoW")

    service = EventIngestionService(unit_of_work_factory)

    with pytest.raises(UnsupportedSchemaVersionError):
        ingest(service, schema_version=2)

    assert factory_called is False


def test_resolved_replay_skips_session_read_accept_and_commit() -> None:
    original = stored_event()
    service, calls = recording_service(
        None,
        resolved=EventAcceptance(
            EventAcceptanceStatus.ALREADY_PROCESSED,
            original,
        ),
    )

    result = ingest(service)

    assert result.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert result.event is original
    assert result.event.received_at == RECEIVED_AT
    assert calls == ["enter", "resolve_existing", "exit"]


def test_early_conflict_does_not_override_missing_session() -> None:
    service, calls = recording_service(
        None,
        resolved=EventAcceptance(
            EventAcceptanceStatus.CONFLICT,
            stored_event(),
        ),
    )

    with pytest.raises(SessionNotFoundError):
        ingest(service, session_id=OTHER_SESSION_ID)

    assert calls == ["enter", "resolve_existing", "get_for_event_ingestion", "exit"]


def test_early_conflict_does_not_override_temporal_validation() -> None:
    service, calls = recording_service(
        session(status=SessionStatus.COMPLETED),
        resolved=EventAcceptance(
            EventAcceptanceStatus.CONFLICT,
            stored_event(),
        ),
    )

    with pytest.raises(EventOutsideSessionError):
        ingest(service, occurred_at=ENDED_AT + timedelta(microseconds=1))

    assert calls == ["enter", "resolve_existing", "get_for_event_ingestion", "exit"]


def test_creation_uses_transactional_order_and_commits_once() -> None:
    service, calls = recording_service(session())

    result = ingest(service)

    assert result.status is EventAcceptanceStatus.CREATED
    assert calls == [
        "enter",
        "resolve_existing",
        "get_for_event_ingestion",
        "accept",
        "commit",
        "exit",
    ]


def test_accept_race_replay_commits_and_returns_winner() -> None:
    winner = stored_event()
    service, calls = recording_service(
        session(),
        accepted=EventAcceptance(
            EventAcceptanceStatus.ALREADY_PROCESSED,
            winner,
        ),
    )

    result = ingest(service)

    assert result.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert result.event is winner
    assert result.event.received_at == RECEIVED_AT
    assert calls.count("commit") == 1


def test_accept_conflict_raises_without_commit() -> None:
    service, calls = recording_service(
        session(),
        accepted=EventAcceptance(
            EventAcceptanceStatus.CONFLICT,
            stored_event(),
        ),
    )

    with pytest.raises(EventConflictError):
        ingest(service)

    assert "commit" not in calls


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
    events = InMemoryEventRepository()
    service = EventIngestionService(
        lambda: InMemoryUnitOfWork(sessions, events),
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
    events = InMemoryEventRepository()
    service = EventIngestionService(
        lambda: InMemoryUnitOfWork(sessions, events),
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
