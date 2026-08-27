from datetime import datetime, timedelta, timezone
from uuid import RFC_4122, UUID, uuid4

import pytest

from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
STARTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def active_session() -> MonitoringSession:
    return MonitoringSession(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        started_at=STARTED_AT,
    )


def test_active_session_has_no_end_time() -> None:
    session = active_session()

    assert session.status is SessionStatus.ACTIVE
    assert session.ended_at is None


def test_semantically_equivalent_utc_timezone_is_accepted() -> None:
    equivalent_utc = timezone(timedelta(0), name="Equivalent UTC")

    session = MonitoringSession(
        session_id=SESSION_ID,
        status=SessionStatus.ACTIVE,
        started_at=datetime(2026, 8, 27, 12, 0, tzinfo=equivalent_utc),
    )

    assert session.started_at.utcoffset() == timedelta(0)


def test_completion_returns_completed_session_and_preserves_identity() -> None:
    session = active_session()
    completed_at = STARTED_AT + timedelta(minutes=30)

    completed = session.complete(completed_at)

    assert session.status is SessionStatus.ACTIVE
    assert session.ended_at is None

    assert completed is not session
    assert completed.status is SessionStatus.COMPLETED
    assert completed.session_id == SESSION_ID
    assert completed.started_at == STARTED_AT
    assert completed.ended_at == completed_at


def test_repeated_completion_preserves_first_completion() -> None:
    first_completion = STARTED_AT + timedelta(minutes=30)
    completed = active_session().complete(first_completion)

    repeated = completed.complete(first_completion + timedelta(minutes=5))

    assert repeated is completed
    assert repeated.ended_at == first_completion


def test_active_session_with_end_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="ACTIVE session"):
        MonitoringSession(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            started_at=STARTED_AT,
            ended_at=STARTED_AT,
        )


def test_completed_session_without_end_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="COMPLETED session"):
        MonitoringSession(
            session_id=SESSION_ID,
            status=SessionStatus.COMPLETED,
            started_at=STARTED_AT,
        )


@pytest.mark.parametrize(
    "invalid_started_at",
    [
        datetime(2026, 8, 27, 12, 0),
        datetime(2026, 8, 27, 12, 0, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_non_utc_start_time_is_rejected(invalid_started_at: datetime) -> None:
    with pytest.raises(ValueError, match="started_at"):
        MonitoringSession(
            session_id=SESSION_ID,
            status=SessionStatus.ACTIVE,
            started_at=invalid_started_at,
        )


@pytest.mark.parametrize(
    "invalid_ended_at",
    [
        datetime(2026, 8, 27, 12, 30),
        datetime(2026, 8, 27, 12, 30, tzinfo=timezone(timedelta(hours=-3))),
    ],
)
def test_non_utc_end_time_is_rejected(invalid_ended_at: datetime) -> None:
    with pytest.raises(ValueError, match="ended_at"):
        MonitoringSession(
            session_id=SESSION_ID,
            status=SessionStatus.COMPLETED,
            started_at=STARTED_AT,
            ended_at=invalid_ended_at,
        )


def test_end_time_before_start_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="earlier"):
        MonitoringSession(
            session_id=SESSION_ID,
            status=SessionStatus.COMPLETED,
            started_at=STARTED_AT,
            ended_at=STARTED_AT - timedelta(microseconds=1),
        )


def test_non_uuid7_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="UUIDv7"):
        MonitoringSession(
            session_id=uuid4(),
            status=SessionStatus.ACTIVE,
            started_at=STARTED_AT,
        )


def test_uuid7_generator_returns_unique_rfc_variant_uuid7_values() -> None:
    first = uuid7()
    second = uuid7()

    assert isinstance(first, UUID)
    assert first.version == 7
    assert first.variant == RFC_4122
    assert second.version == 7
    assert first != second

