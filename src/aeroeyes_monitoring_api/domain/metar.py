from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


class MetarReportType(StrEnum):
    METAR = "METAR"
    SPECI = "SPECI"


class FlightCategory(StrEnum):
    VFR = "VFR"
    MVFR = "MVFR"
    IFR = "IFR"
    LIFR = "LIFR"


def _normalize_station_icao(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("station_icao must be a string")

    normalized = value.strip().upper()
    if len(normalized) != 4 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError(
            "station_icao must be exactly 4 ASCII alphabetic characters"
        )
    return normalized


def _require_optional_finite(value: float | None, field_name: str) -> None:
    if value is not None and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise ValueError(f"{field_name} must be a finite number or None")


@dataclass(frozen=True, slots=True)
class MetarObservation:
    station_icao: str
    report_type: MetarReportType
    observed_at: datetime
    raw_text: str

    flight_category: FlightCategory | None = None

    temperature_c: float | None = None
    dewpoint_c: float | None = None

    wind_direction_deg: int | None = None
    wind_variable: bool = False
    wind_speed_kt: float | None = None
    wind_gust_kt: float | None = None

    visibility_sm: float | None = None
    visibility_greater_than: bool = False

    weather: str | None = None
    ceiling_ft_agl: int | None = None

    altimeter_hpa: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "station_icao",
            _normalize_station_icao(self.station_icao),
        )

        if not isinstance(self.report_type, MetarReportType):
            raise ValueError("report_type must be a MetarReportType")
        if (
            not isinstance(self.observed_at, datetime)
            or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must be a timezone-aware datetime")
        if not isinstance(self.raw_text, str) or not self.raw_text.strip():
            raise ValueError("raw_text must be a non-empty string")
        object.__setattr__(self, "raw_text", self.raw_text.strip())

        if self.flight_category is not None and not isinstance(
            self.flight_category, FlightCategory
        ):
            raise ValueError("flight_category must be a FlightCategory or None")

        if self.wind_direction_deg is not None:
            if type(self.wind_direction_deg) is not int or not (
                0 <= self.wind_direction_deg <= 360
            ):
                raise ValueError(
                    "wind_direction_deg must be an integer from 0 to 360 or None"
                )
        if type(self.wind_variable) is not bool:
            raise ValueError("wind_variable must be a boolean")
        if self.wind_variable and self.wind_direction_deg is not None:
            raise ValueError("variable wind cannot have a numeric direction")
        if type(self.visibility_greater_than) is not bool:
            raise ValueError("visibility_greater_than must be a boolean")

        for field_name in (
            "temperature_c",
            "dewpoint_c",
            "wind_speed_kt",
            "wind_gust_kt",
            "visibility_sm",
            "altimeter_hpa",
        ):
            _require_optional_finite(getattr(self, field_name), field_name)

        for field_name in ("wind_speed_kt", "wind_gust_kt", "visibility_sm"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} cannot be negative")
        if self.ceiling_ft_agl is not None and (
            type(self.ceiling_ft_agl) is not int or self.ceiling_ft_agl < 0
        ):
            raise ValueError("ceiling_ft_agl must be a non-negative integer or None")
        if self.altimeter_hpa is not None and self.altimeter_hpa <= 0:
            raise ValueError("altimeter_hpa must be positive")
