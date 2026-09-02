from uuid import UUID

from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)

FIRST_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
SECOND_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000002")


def test_missing_context_returns_none() -> None:
    repository = InMemorySessionContextRepository()

    assert repository.get(FIRST_SESSION_ID) is None


def test_first_save_stores_and_returns_context() -> None:
    repository = InMemorySessionContextRepository()
    context = SessionContext(session_id=FIRST_SESSION_ID, flight_number="LA8084")

    stored = repository.save(context)

    assert stored is context
    assert repository.get(FIRST_SESSION_ID) is context


def test_save_for_same_session_performs_complete_replacement() -> None:
    repository = InMemorySessionContextRepository()
    existing = SessionContext(
        session_id=FIRST_SESSION_ID,
        flight_number="LA8084",
        departure_icao="SBGR",
        destination_icao="SBGL",
    )
    replacement = SessionContext(
        session_id=FIRST_SESSION_ID,
        flight_number="AD1234",
        departure_icao="SBSP",
        destination_icao="SBRJ",
    )
    repository.save(existing)

    stored = repository.save(replacement)

    assert stored is replacement
    assert repository.get(FIRST_SESSION_ID) is replacement


def test_replacement_clears_previously_populated_fields() -> None:
    repository = InMemorySessionContextRepository()
    repository.save(
        SessionContext(
            session_id=FIRST_SESSION_ID,
            flight_number="LA8084",
            departure_icao="SBGR",
            destination_icao="SBGL",
        )
    )
    replacement = SessionContext(
        session_id=FIRST_SESSION_ID,
        departure_icao="SBSP",
    )

    repository.save(replacement)

    assert repository.get(FIRST_SESSION_ID) == replacement
    assert replacement.flight_number is None
    assert replacement.destination_icao is None


def test_contexts_for_different_sessions_remain_independent() -> None:
    repository = InMemorySessionContextRepository()
    first = SessionContext(session_id=FIRST_SESSION_ID, departure_icao="SBGR")
    second = SessionContext(session_id=SECOND_SESSION_ID, destination_icao="SBGL")

    repository.save(first)
    repository.save(second)

    assert repository.get(FIRST_SESSION_ID) is first
    assert repository.get(SECOND_SESSION_ID) is second


def test_delete_existing_context_returns_true_and_removes_it() -> None:
    repository = InMemorySessionContextRepository()
    repository.save(SessionContext(session_id=FIRST_SESSION_ID))

    deleted = repository.delete(FIRST_SESSION_ID)

    assert deleted is True
    assert repository.get(FIRST_SESSION_ID) is None


def test_delete_missing_context_returns_false() -> None:
    repository = InMemorySessionContextRepository()

    assert repository.delete(FIRST_SESSION_ID) is False
