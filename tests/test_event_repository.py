from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
    IngestedAttentionEvent,
)
from aeroeyes_monitoring_api.event_repository import (
    EventAcceptanceStatus,
    InMemoryEventRepository,
)

EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000010")
SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
OTHER_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000002")
OCCURRED_AT = datetime(2026, 8, 27, 12, 10, tzinfo=timezone.utc)
RECEIVED_AT = datetime(2026, 8, 27, 12, 11, tzinfo=timezone.utc)


def event(**changes: object) -> IngestedAttentionEvent:
    values = {
        "event_id": EVENT_ID,
        "session_id": SESSION_ID,
        "occurred_at": OCCURRED_AT,
        "received_at": RECEIVED_AT,
        "state": AttentionState.ATTENTION,
        "severity": AttentionSeverity.MEDIUM,
        "face_detected": True,
        "eye_state": EyeState.CLOSED,
        "closed_duration_ms": 1250,
        "schema_version": 1,
    }
    values.update(changes)
    return IngestedAttentionEvent(**values)


def test_first_candidate_is_created() -> None:
    candidate = event()

    result = InMemoryEventRepository().accept(candidate)

    assert result.status is EventAcceptanceStatus.CREATED
    assert result.event is candidate


def test_replay_returns_original_event_and_received_at() -> None:
    repository = InMemoryEventRepository()
    original = event()
    replay = replace(original, received_at=RECEIVED_AT + timedelta(minutes=1))
    repository.accept(original)

    result = repository.accept(replay)

    assert result.status is EventAcceptanceStatus.ALREADY_PROCESSED
    assert result.event is original
    assert result.event.received_at == RECEIVED_AT


def test_changed_occurred_at_conflicts_without_replacing_original() -> None:
    repository = InMemoryEventRepository()
    original = event()
    repository.accept(original)

    result = repository.accept(
        replace(original, occurred_at=OCCURRED_AT + timedelta(seconds=1))
    )

    assert result.status is EventAcceptanceStatus.CONFLICT
    assert result.event is original
    assert repository.accept(original).status is EventAcceptanceStatus.ALREADY_PROCESSED


def test_changed_state_conflicts() -> None:
    repository = InMemoryEventRepository()
    original = event()
    repository.accept(original)

    result = repository.accept(replace(original, state=AttentionState.CRITICAL))

    assert result.status is EventAcceptanceStatus.CONFLICT
    assert result.event is original


def test_different_session_conflicts() -> None:
    repository = InMemoryEventRepository()
    original = event()
    repository.accept(original)

    result = repository.accept(replace(original, session_id=OTHER_SESSION_ID))

    assert result.status is EventAcceptanceStatus.CONFLICT
    assert result.event is original


def test_concurrent_identical_candidates_create_one_logical_event() -> None:
    repository = InMemoryEventRepository()
    candidate = event()
    barrier = Barrier(4)

    def accept() -> object:
        barrier.wait()
        return repository.accept(candidate)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: accept(), range(4)))

    statuses = [result.status for result in results]
    assert statuses.count(EventAcceptanceStatus.CREATED) == 1
    assert statuses.count(EventAcceptanceStatus.ALREADY_PROCESSED) == 3
    assert all(result.event is candidate for result in results)


def test_concurrent_conflicting_candidates_keep_one_winner() -> None:
    repository = InMemoryEventRepository()
    candidates = (
        event(state=AttentionState.ATTENTION),
        event(state=AttentionState.CRITICAL),
    )
    barrier = Barrier(2)

    def accept(candidate: IngestedAttentionEvent) -> object:
        barrier.wait()
        return repository.accept(candidate)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(accept, candidates))

    assert {result.status for result in results} == {
        EventAcceptanceStatus.CREATED,
        EventAcceptanceStatus.CONFLICT,
    }
    winner = next(
        result.event
        for result in results
        if result.status is EventAcceptanceStatus.CREATED
    )
    assert all(result.event is winner for result in results)
    assert repository.accept(winner).event is winner
