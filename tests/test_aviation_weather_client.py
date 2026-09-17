import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from aeroeyes_monitoring_api.aviation_weather_client import (
    DEFAULT_USER_AGENT,
    AviationWeatherClient,
    AviationWeatherContractError,
    AviationWeatherRateLimitError,
    AviationWeatherRequestError,
    AviationWeatherUnavailableError,
)
from aeroeyes_monitoring_api.domain.metar import FlightCategory, MetarReportType


FIXTURES = Path(__file__).parent / "fixtures" / "aviation_weather"
MISSING = object()


def _fixture(name: str) -> list[dict[str, Any]]:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _client_for_response(
    response: httpx.Response,
) -> tuple[AviationWeatherClient, httpx.Client]:
    transport = httpx.MockTransport(lambda request: response)
    http_client = httpx.Client(transport=transport)
    return AviationWeatherClient(http_client), http_client


def test_sbgr_provider_snapshot_is_normalized() -> None:
    adapter, http_client = _client_for_response(
        httpx.Response(200, json=_fixture("sbgr"))
    )
    try:
        observation = adapter.get_metar("sbgr")
    finally:
        http_client.close()

    assert observation is not None
    assert observation.report_type is MetarReportType.METAR
    assert observation.flight_category is FlightCategory.MVFR
    assert (observation.visibility_sm, observation.visibility_greater_than) == (
        6.0,
        True,
    )
    assert observation.weather is None
    assert observation.ceiling_ft_agl == 2000
    assert observation.altimeter_hpa == 1025.0


def test_sbrj_provider_snapshot_is_normalized() -> None:
    adapter, http_client = _client_for_response(
        httpx.Response(200, json=_fixture("sbrj"))
    )
    try:
        observation = adapter.get_metar("SBRJ")
    finally:
        http_client.close()

    assert observation is not None
    assert observation.report_type is MetarReportType.SPECI
    assert observation.flight_category is FlightCategory.IFR
    assert (observation.visibility_sm, observation.visibility_greater_than) == (
        2.49,
        False,
    )
    assert observation.weather == "-RA BR"
    assert observation.ceiling_ft_agl == 1000
    assert observation.altimeter_hpa == 1022.0


def test_kjfk_snapshot_preserves_calm_wind_and_provider_altimeter_hpa() -> None:
    adapter, http_client = _client_for_response(
        httpx.Response(200, json=_fixture("kjfk"))
    )
    try:
        observation = adapter.get_metar("KJFK")
    finally:
        http_client.close()

    assert observation is not None
    assert observation.flight_category is FlightCategory.VFR
    assert (observation.wind_direction_deg, observation.wind_variable) == (0, False)
    assert observation.wind_speed_kt == 0.0
    assert (observation.visibility_sm, observation.visibility_greater_than) == (
        10.0,
        True,
    )
    assert observation.ceiling_ft_agl is None
    assert observation.altimeter_hpa == 1017.7
    assert observation.observed_at == datetime(
        2026, 9, 7, 1, 51, tzinfo=timezone.utc
    )


def test_variable_wind_optional_gust_and_lifr_are_normalized() -> None:
    payload = _fixture("sbgr")
    payload[0].update({"wdir": "VRB", "wgst": 21, "fltCat": "LIFR"})
    adapter, http_client = _client_for_response(httpx.Response(200, json=payload))
    try:
        observation = adapter.get_metar("SBGR")
    finally:
        http_client.close()

    assert observation is not None
    assert (observation.wind_direction_deg, observation.wind_variable) == (
        None,
        True,
    )
    assert observation.wind_gust_kt == 21.0
    assert observation.flight_category is FlightCategory.LIFR


def test_latest_matching_observation_is_selected_without_relying_on_order() -> None:
    older = _fixture("sbgr")[0]
    newest = {**older, "obsTime": older["obsTime"] + 60, "rawOb": "newest"}
    middle = {**older, "obsTime": older["obsTime"] + 30, "rawOb": "middle"}
    adapter, http_client = _client_for_response(
        httpx.Response(200, json=[newest, older, middle])
    )
    try:
        observation = adapter.get_metar("SBGR")
    finally:
        http_client.close()

    assert observation is not None
    assert observation.raw_text == "newest"


@pytest.mark.parametrize("response", [httpx.Response(204), httpx.Response(200, json=[])])
def test_no_current_observation_returns_none(response: httpx.Response) -> None:
    adapter, http_client = _client_for_response(response)
    try:
        assert adapter.get_metar("SBGR") is None
    finally:
        http_client.close()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"{"),
        httpx.Response(200, json={"icaoId": "SBGR"}),
    ],
)
def test_invalid_json_or_top_level_shape_is_a_contract_error(
    response: httpx.Response,
) -> None:
    adapter, http_client = _client_for_response(response)
    try:
        with pytest.raises(AviationWeatherContractError):
            adapter.get_metar("SBGR")
    finally:
        http_client.close()


def test_wrong_station_is_a_contract_error() -> None:
    adapter, http_client = _client_for_response(
        httpx.Response(200, json=_fixture("kjfk"))
    )
    try:
        with pytest.raises(AviationWeatherContractError, match="requested station"):
            adapter.get_metar("SBGR")
    finally:
        http_client.close()


def test_mixed_requested_and_foreign_stations_are_a_contract_error() -> None:
    payload = _fixture("sbgr") + _fixture("kjfk")
    adapter, http_client = _client_for_response(httpx.Response(200, json=payload))
    try:
        with pytest.raises(AviationWeatherContractError, match="requested station"):
            adapter.get_metar("SBGR")
    finally:
        http_client.close()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("obsTime", "not-an-epoch"),
        ("obsTime", float("inf")),
        ("metarType", "AUTO"),
        ("fltCat", "UNKNOWN"),
        ("rawOb", MISSING),
        ("rawOb", None),
        ("icaoId", "SBG1"),
        ("temp", "warm"),
    ],
    ids=[
        "invalid-obsTime-type",
        "non-finite-obsTime",
        "unsupported-metarType",
        "unsupported-fltCat",
        "missing-rawOb",
        "null-rawOb",
        "malformed-icaoId",
        "malformed-optional-number",
    ],
)
def test_malformed_provider_core_fields_are_contract_errors(
    field_name: str,
    invalid_value: object,
) -> None:
    payload = _fixture("sbgr")
    if invalid_value is MISSING:
        payload[0].pop(field_name)
    else:
        payload[0][field_name] = invalid_value
    response = httpx.Response(200, content=json.dumps(payload).encode())
    adapter, http_client = _client_for_response(response)
    try:
        with pytest.raises(AviationWeatherContractError):
            adapter.get_metar("SBGR")
    finally:
        http_client.close()


@pytest.mark.parametrize("visibility", ["many", "10++", -1, "Infinity", {}])
def test_malformed_visibility_is_a_contract_error(visibility: object) -> None:
    payload = _fixture("sbgr")
    payload[0]["visib"] = visibility
    adapter, http_client = _client_for_response(httpx.Response(200, json=payload))
    try:
        with pytest.raises(AviationWeatherContractError, match="visibility"):
            adapter.get_metar("SBGR")
    finally:
        http_client.close()


def test_plain_numeric_visibility_string_is_accepted() -> None:
    payload = _fixture("sbgr")
    payload[0]["visib"] = "3.5"
    adapter, http_client = _client_for_response(httpx.Response(200, json=payload))
    try:
        observation = adapter.get_metar("SBGR")
    finally:
        http_client.close()

    assert observation is not None
    assert (observation.visibility_sm, observation.visibility_greater_than) == (
        3.5,
        False,
    )


def test_missing_optional_fields_produce_none_and_false_defaults() -> None:
    payload = [
        {
            "icaoId": "SBGR",
            "obsTime": 1788746400,
            "metarType": "METAR",
            "rawOb": "METAR SBGR 070200Z AUTO",
        }
    ]
    adapter, http_client = _client_for_response(httpx.Response(200, json=payload))
    try:
        observation = adapter.get_metar("SBGR")
    finally:
        http_client.close()

    assert observation is not None
    assert observation.flight_category is None
    assert observation.temperature_c is None
    assert observation.wind_direction_deg is None
    assert observation.wind_variable is False
    assert observation.visibility_sm is None
    assert observation.visibility_greater_than is False
    assert observation.ceiling_ft_agl is None


def test_malformed_cloud_layers_do_not_fabricate_a_ceiling() -> None:
    payload = _fixture("sbgr")
    payload[0]["clouds"] = [
        {"cover": "FEW", "base": 500},
        {"cover": "BKN", "base": "low"},
        {"cover": "OVC", "base": -1},
        "malformed",
    ]
    adapter, http_client = _client_for_response(httpx.Response(200, json=payload))
    try:
        observation = adapter.get_metar("SBGR")
    finally:
        http_client.close()

    assert observation is not None
    assert observation.ceiling_ft_agl is None


def test_transport_failure_is_unavailable() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(fail))
    adapter = AviationWeatherClient(http_client)
    try:
        with pytest.raises(AviationWeatherUnavailableError):
            adapter.get_metar("SBGR")
    finally:
        http_client.close()


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, AviationWeatherRequestError),
        (403, AviationWeatherRequestError),
        (404, AviationWeatherRequestError),
        (429, AviationWeatherRateLimitError),
        (500, AviationWeatherUnavailableError),
        (503, AviationWeatherUnavailableError),
    ],
)
def test_http_statuses_map_to_provider_errors(
    status: int, error_type: type[Exception]
) -> None:
    adapter, http_client = _client_for_response(httpx.Response(status))
    try:
        with pytest.raises(error_type):
            adapter.get_metar("SBGR")
    finally:
        http_client.close()


@pytest.mark.parametrize("station", ["SBG", "SBG1", "SÁGR", ""])
def test_invalid_requested_icao_does_not_issue_http(station: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AviationWeatherClient(http_client)
    try:
        with pytest.raises(ValueError, match="ASCII alphabetic"):
            adapter.get_metar(station)
    finally:
        http_client.close()

    assert calls == 0


def test_request_contract_and_supplied_client_lifecycle() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AviationWeatherClient(http_client)

    assert adapter.get_metar(" sbgr ") is None
    assert not http_client.is_closed
    assert len(captured) == 1
    assert captured[0].url.params["ids"] == "SBGR"
    assert captured[0].url.params["format"] == "json"
    assert captured[0].headers["User-Agent"] == DEFAULT_USER_AGENT
    http_client.close()
