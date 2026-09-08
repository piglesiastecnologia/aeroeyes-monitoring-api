from collections.abc import Mapping
from datetime import datetime, timezone
from math import isfinite
from typing import Any

import httpx

from aeroeyes_monitoring_api.domain.metar import (
    FlightCategory,
    MetarObservation,
    MetarReportType,
)


AVIATION_WEATHER_METAR_URL = "https://aviationweather.gov/api/data/metar"
DEFAULT_USER_AGENT = "AeroEyes-MVP/0.1"


class AviationWeatherError(Exception):
    """Base error for failures at the AviationWeather provider boundary."""


class AviationWeatherRequestError(AviationWeatherError):
    """The provider rejected the outbound request."""


class AviationWeatherRateLimitError(AviationWeatherError):
    """The provider rate-limited the outbound request."""


class AviationWeatherUnavailableError(AviationWeatherError):
    """The provider could not be reached or was unavailable."""


class AviationWeatherContractError(AviationWeatherError):
    """The provider response did not satisfy the expected METAR contract."""


def _normalize_requested_icao(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("station_icao must be a string")

    normalized = value.strip().upper()
    if len(normalized) != 4 or not normalized.isascii() or not normalized.isalpha():
        raise ValueError(
            "station_icao must be exactly 4 ASCII alphabetic characters"
        )
    return normalized


def _required_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise AviationWeatherContractError(
            f"provider field {field_name!r} must be a non-empty string"
        )
    return value.strip()


def _optional_number(payload: Mapping[str, Any], field_name: str) -> float | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise AviationWeatherContractError(
            f"provider field {field_name!r} must be a finite number or null"
        )
    return float(value)


def _parse_observed_at(payload: Mapping[str, Any]) -> datetime:
    value = payload.get("obsTime")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise AviationWeatherContractError(
            "provider field 'obsTime' must be finite UNIX epoch seconds"
        )
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise AviationWeatherContractError(
            "provider field 'obsTime' is outside the supported datetime range"
        ) from exc


def _parse_visibility(value: Any) -> tuple[float | None, bool]:
    if value is None:
        return None, False

    greater_than = False
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("+"):
            greater_than = True
            normalized = normalized[:-1]
        if not normalized:
            raise AviationWeatherContractError("provider visibility is malformed")
        try:
            visibility = float(normalized)
        except ValueError as exc:
            raise AviationWeatherContractError(
                "provider visibility is malformed"
            ) from exc
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AviationWeatherContractError("provider visibility is malformed")
    else:
        visibility = float(value)

    if not isfinite(visibility) or visibility < 0:
        raise AviationWeatherContractError("provider visibility is malformed")
    return visibility, greater_than


def _parse_wind_direction(value: Any) -> tuple[int | None, bool]:
    if value is None:
        return None, False
    if value == "VRB":
        return None, True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AviationWeatherContractError("provider wind direction is malformed")
    if not isfinite(value) or not float(value).is_integer():
        raise AviationWeatherContractError("provider wind direction is malformed")

    direction = int(value)
    if not 0 <= direction <= 360:
        raise AviationWeatherContractError("provider wind direction is malformed")
    return direction, False


def _parse_optional_text(payload: Mapping[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AviationWeatherContractError(
            f"provider field {field_name!r} must be a string or null"
        )
    return value.strip() or None


def _derive_ceiling(payload: Mapping[str, Any]) -> int | None:
    clouds = payload.get("clouds")
    if clouds is None:
        return None
    if not isinstance(clouds, list):
        return None

    valid_bases: list[int] = []
    for layer in clouds:
        if not isinstance(layer, Mapping) or layer.get("cover") not in {
            "BKN",
            "OVC",
            "VV",
        }:
            continue
        base = layer.get("base")
        if (
            isinstance(base, bool)
            or not isinstance(base, (int, float))
            or not isfinite(base)
            or not float(base).is_integer()
            or base < 0
        ):
            continue
        valid_bases.append(int(base))

    return min(valid_bases, default=None)


def _parse_observation(payload: Mapping[str, Any]) -> MetarObservation:
    station_icao = _required_string(payload, "icaoId").upper()
    if (
        len(station_icao) != 4
        or not station_icao.isascii()
        or not station_icao.isalpha()
    ):
        raise AviationWeatherContractError("provider field 'icaoId' is malformed")

    try:
        report_type = MetarReportType(_required_string(payload, "metarType"))
    except ValueError as exc:
        raise AviationWeatherContractError(
            "provider field 'metarType' is unsupported"
        ) from exc

    category_value = payload.get("fltCat")
    if category_value is None:
        flight_category = None
    else:
        try:
            flight_category = FlightCategory(category_value)
        except (TypeError, ValueError) as exc:
            raise AviationWeatherContractError(
                "provider field 'fltCat' is unsupported"
            ) from exc

    visibility_sm, visibility_greater_than = _parse_visibility(payload.get("visib"))
    wind_direction_deg, wind_variable = _parse_wind_direction(payload.get("wdir"))

    try:
        return MetarObservation(
            station_icao=station_icao,
            report_type=report_type,
            observed_at=_parse_observed_at(payload),
            raw_text=_required_string(payload, "rawOb"),
            flight_category=flight_category,
            temperature_c=_optional_number(payload, "temp"),
            dewpoint_c=_optional_number(payload, "dewp"),
            wind_direction_deg=wind_direction_deg,
            wind_variable=wind_variable,
            wind_speed_kt=_optional_number(payload, "wspd"),
            wind_gust_kt=_optional_number(payload, "wgst"),
            visibility_sm=visibility_sm,
            visibility_greater_than=visibility_greater_than,
            weather=_parse_optional_text(payload, "wxString"),
            ceiling_ft_agl=_derive_ceiling(payload),
            altimeter_hpa=_optional_number(payload, "altim"),
        )
    except ValueError as exc:
        raise AviationWeatherContractError(
            "provider observation violates the AeroEyes METAR contract"
        ) from exc


class AviationWeatherClient:
    def __init__(
        self,
        http_client: httpx.Client,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._http_client = http_client
        self._user_agent = user_agent

    def get_metar(self, station_icao: str) -> MetarObservation | None:
        requested_icao = _normalize_requested_icao(station_icao)
        try:
            response = self._http_client.get(
                AVIATION_WEATHER_METAR_URL,
                params={"ids": requested_icao, "format": "json"},
                headers={"User-Agent": self._user_agent},
            )
        except httpx.RequestError as exc:
            raise AviationWeatherUnavailableError(
                "AviationWeather provider is unavailable"
            ) from exc

        if response.status_code == 204:
            return None
        if response.status_code == 429:
            raise AviationWeatherRateLimitError(
                "AviationWeather provider rate limit exceeded"
            )
        if 500 <= response.status_code:
            raise AviationWeatherUnavailableError(
                "AviationWeather provider is unavailable"
            )
        if response.status_code != 200:
            raise AviationWeatherRequestError(
                f"AviationWeather request failed with status {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AviationWeatherContractError(
                "AviationWeather response is not valid JSON"
            ) from exc
        if not isinstance(payload, list):
            raise AviationWeatherContractError(
                "AviationWeather response must be a JSON list"
            )
        if not payload:
            return None

        matching: list[MetarObservation] = []
        for candidate in payload:
            if not isinstance(candidate, Mapping):
                raise AviationWeatherContractError(
                    "AviationWeather observation must be a JSON object"
                )
            observation = _parse_observation(candidate)
            if observation.station_icao != requested_icao:
                raise AviationWeatherContractError(
                    "AviationWeather returned an observation for a station other "
                    "than the requested station"
                )
            matching.append(observation)

        if not matching:
            raise AviationWeatherContractError(
                "AviationWeather returned no observation for the requested station"
            )
        return max(matching, key=lambda observation: observation.observed_at)
