from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest

from aeroeyes_monitoring_api.domain.session_context import SessionContext

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")


def test_valid_context_is_canonical() -> None:
    context = SessionContext(
        session_id=SESSION_ID,
        flight_number=" la8084 ",
        departure_icao=" sbgr ",
        destination_icao=" sbgl ",
    )

    assert context == SessionContext(
        session_id=SESSION_ID,
        flight_number="LA8084",
        departure_icao="SBGR",
        destination_icao="SBGL",
    )


@pytest.mark.parametrize("invalid_session_id", [uuid4(), str(SESSION_ID)])
def test_session_id_must_be_uuid7(invalid_session_id: object) -> None:
    with pytest.raises(ValueError, match="UUIDv7"):
        SessionContext(session_id=invalid_session_id)  # type: ignore[arg-type]


def test_flight_number_is_trimmed_and_uppercased() -> None:
    context = SessionContext(session_id=SESSION_ID, flight_number="  azu 123  ")

    assert context.flight_number == "AZU 123"


def test_blank_flight_number_becomes_none() -> None:
    context = SessionContext(session_id=SESSION_ID, flight_number=" \t\n ")

    assert context.flight_number is None


def test_icao_values_are_trimmed_and_uppercased() -> None:
    context = SessionContext(
        session_id=SESSION_ID,
        departure_icao=" sbsp ",
        destination_icao=" sbrj ",
    )

    assert context.departure_icao == "SBSP"
    assert context.destination_icao == "SBRJ"


@pytest.mark.parametrize("field_name", ["departure_icao", "destination_icao"])
def test_blank_icao_becomes_none(field_name: str) -> None:
    context = SessionContext(session_id=SESSION_ID, **{field_name: "   "})

    assert getattr(context, field_name) is None


@pytest.mark.parametrize("invalid_icao", ["SBG", "SBGRR"])
def test_icao_with_invalid_length_is_rejected(invalid_icao: str) -> None:
    with pytest.raises(ValueError, match="exactly 4"):
        SessionContext(session_id=SESSION_ID, departure_icao=invalid_icao)


@pytest.mark.parametrize("invalid_icao", ["SB1R", "S-GR", "SÁGR"])
def test_non_ascii_or_non_alphabetic_icao_is_rejected(invalid_icao: str) -> None:
    with pytest.raises(ValueError, match="ASCII alphabetic"):
        SessionContext(session_id=SESSION_ID, destination_icao=invalid_icao)


def test_all_null_context_is_valid() -> None:
    context = SessionContext(session_id=SESSION_ID)

    assert context.flight_number is None
    assert context.departure_icao is None
    assert context.destination_icao is None


def test_context_is_immutable() -> None:
    context = SessionContext(session_id=SESSION_ID)

    with pytest.raises(FrozenInstanceError):
        context.flight_number = "LA8084"  # type: ignore[misc]
