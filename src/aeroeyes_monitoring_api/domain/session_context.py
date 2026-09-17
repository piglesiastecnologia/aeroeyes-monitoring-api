from dataclasses import dataclass
from uuid import UUID


def _normalize_optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or None")

    normalized = value.strip().upper()
    return normalized or None


def _normalize_icao(value: str | None, field_name: str) -> str | None:
    normalized = _normalize_optional_text(value, field_name)
    if normalized is None:
        return None
    if len(normalized) != 4 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError(
            f"{field_name} must be exactly 4 ASCII alphabetic characters"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class SessionContext:
    session_id: UUID
    flight_number: str | None = None
    departure_icao: str | None = None
    destination_icao: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, UUID) or self.session_id.version != 7:
            raise ValueError("session_id must be a UUIDv7")

        object.__setattr__(
            self,
            "flight_number",
            _normalize_optional_text(self.flight_number, "flight_number"),
        )
        object.__setattr__(
            self,
            "departure_icao",
            _normalize_icao(self.departure_icao, "departure_icao"),
        )
        object.__setattr__(
            self,
            "destination_icao",
            _normalize_icao(self.destination_icao, "destination_icao"),
        )
