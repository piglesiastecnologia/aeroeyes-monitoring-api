from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
    IngestedAttentionEvent,
)

EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000010")
OTHER_EVENT_ID = UUID("01890f3d-2d00-7000-8000-000000000011")
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


def test_valid_event_is_immutable() -> None:
    ingested = event()

    with pytest.raises(FrozenInstanceError):
        ingested.state = AttentionState.NORMAL  # type: ignore[misc]


@pytest.mark.parametrize("field_name", ["event_id", "session_id"])
def test_identity_must_be_uuid7(field_name: str) -> None:
    with pytest.raises(ValueError, match="UUIDv7"):
        event(**{field_name: uuid4()})


def test_equivalent_utc_timezones_are_accepted() -> None:
    equivalent_utc = timezone(timedelta(0), name="Equivalent UTC")

    ingested = event(
        occurred_at=OCCURRED_AT.astimezone(equivalent_utc),
        received_at=RECEIVED_AT.astimezone(equivalent_utc),
    )

    assert ingested.occurred_at.utcoffset() == timedelta(0)
    assert ingested.received_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("field_name", ["occurred_at", "received_at"])
@pytest.mark.parametrize(
    "invalid_time",
    [
        datetime(2026, 8, 27, 12, 0),
        datetime(2026, 8, 27, 12, 0, tzinfo=timezone(timedelta(hours=-3))),
    ],
)
def test_timestamps_must_be_semantic_utc(
    field_name: str,
    invalid_time: datetime,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        event(**{field_name: invalid_time})


def test_nullable_eye_fields_are_valid() -> None:
    ingested = event(eye_state=None, closed_duration_ms=None)

    assert ingested.eye_state is None
    assert ingested.closed_duration_ms is None


@pytest.mark.parametrize("invalid_duration", [-1, 1.5, True])
def test_closed_duration_must_be_a_non_negative_integer_or_none(
    invalid_duration: object,
) -> None:
    with pytest.raises(ValueError, match="closed_duration_ms"):
        event(closed_duration_ms=invalid_duration)


@pytest.mark.parametrize("invalid_version", [2, 1.0, "1", True])
def test_schema_version_must_be_strict_supported_integer(
    invalid_version: object,
) -> None:
    with pytest.raises(ValueError, match="schema_version"):
        event(schema_version=invalid_version)


def test_semantic_payload_contains_exact_producer_semantics() -> None:
    ingested = event()

    assert ingested.semantic_payload == (
        OCCURRED_AT,
        AttentionState.ATTENTION,
        AttentionSeverity.MEDIUM,
        True,
        EyeState.CLOSED,
        1250,
        1,
    )


def test_semantic_payload_excludes_ids_and_received_at() -> None:
    original = event()
    changed_non_semantic_fields = replace(
        original,
        event_id=OTHER_EVENT_ID,
        session_id=OTHER_SESSION_ID,
        received_at=RECEIVED_AT + timedelta(minutes=1),
    )

    assert changed_non_semantic_fields.semantic_payload == original.semantic_payload
