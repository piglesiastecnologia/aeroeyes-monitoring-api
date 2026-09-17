from datetime import datetime, timezone

from fastapi.testclient import TestClient

from aeroeyes_monitoring_api.aviation_weather_client import (
    AviationWeatherContractError,
    AviationWeatherUnavailableError,
)
from aeroeyes_monitoring_api.domain.metar import (
    FlightCategory,
    MetarObservation,
    MetarReportType,
)
from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.main import create_app
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork


class FakeWeatherClient:
    def __init__(self, results: dict[str, object] | None = None) -> None:
        self.results = results or {}
        self.calls: list[str] = []

    def get_metar(self, station_icao: str) -> MetarObservation | None:
        self.calls.append(station_icao)
        result = self.results.get(station_icao)
        if isinstance(result, Exception):
            raise result
        assert result is None or isinstance(result, MetarObservation)
        return result


def observation(station_icao: str, report_type=MetarReportType.METAR):
    return MetarObservation(
        station_icao=station_icao,
        report_type=report_type,
        observed_at=datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc),
        raw_text=f"{report_type.value} {station_icao} 081230Z",
        flight_category=FlightCategory.MVFR,
        temperature_c=21.0,
        dewpoint_c=18.0,
        wind_direction_deg=120,
        wind_speed_kt=12.0,
        visibility_sm=6.0,
        visibility_greater_than=True,
        weather="-RA",
        ceiling_ft_agl=2000,
        altimeter_hpa=1015.0,
    )


def app_client(provider: FakeWeatherClient) -> TestClient:
    sessions = InMemorySessionRepository()
    contexts = InMemorySessionContextRepository()
    return TestClient(
        create_app(
            unit_of_work_factory=lambda: InMemoryUnitOfWork(
                sessions,
                InMemoryEventRepository(),
                contexts,
            ),
            aviation_weather_client=provider,
        )
    )


def create_session_with_context(client: TestClient, context: dict) -> str:
    session_id = client.post("/sessions").json()["session_id"]
    response = client.put(f"/sessions/{session_id}/context", json=context)
    assert response.status_code == 200
    return session_id


def test_weather_returns_both_normalized_observations_and_serializes_enums_time(
) -> None:
    provider = FakeWeatherClient(
        {
            "SBGR": observation("SBGR"),
            "SBRJ": observation("SBRJ", MetarReportType.SPECI),
        }
    )
    with app_client(provider) as client:
        session_id = create_session_with_context(
            client,
            {"departure_icao": "SBGR", "destination_icao": "SBRJ"},
        )
        response = client.get(f"/sessions/{session_id}/weather")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["departure"]["station_icao"] == "SBGR"
    assert payload["departure"]["observation"]["report_type"] == "METAR"
    assert payload["departure"]["observation"]["flight_category"] == "MVFR"
    assert payload["departure"]["observation"]["observed_at"] == (
        "2026-09-08T12:30:00Z"
    )
    assert payload["destination"]["observation"]["report_type"] == "SPECI"
    assert provider.calls == ["SBGR", "SBRJ"]


def test_weather_all_null_context_returns_two_null_slots() -> None:
    provider = FakeWeatherClient()
    with app_client(provider) as client:
        session_id = create_session_with_context(client, {})
        response = client.get(f"/sessions/{session_id}/weather")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "departure": None,
        "destination": None,
    }
    assert provider.calls == []


def test_configured_airport_with_provider_no_data_has_null_observation() -> None:
    provider = FakeWeatherClient()
    with app_client(provider) as client:
        session_id = create_session_with_context(
            client,
            {"departure_icao": "SBGR"},
        )
        response = client.get(f"/sessions/{session_id}/weather")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "departure": {"station_icao": "SBGR", "observation": None},
        "destination": None,
    }


def test_departure_only_and_destination_only_preserve_slot_meaning() -> None:
    provider = FakeWeatherClient()
    with app_client(provider) as client:
        departure_session = create_session_with_context(
            client, {"departure_icao": "SBGR"}
        )
        destination_session = create_session_with_context(
            client, {"destination_icao": "SBRJ"}
        )
        departure = client.get(f"/sessions/{departure_session}/weather").json()
        destination = client.get(f"/sessions/{destination_session}/weather").json()

    assert departure["departure"]["station_icao"] == "SBGR"
    assert departure["destination"] is None
    assert destination["departure"] is None
    assert destination["destination"]["station_icao"] == "SBRJ"


def test_weather_distinguishes_missing_session_and_missing_context() -> None:
    provider = FakeWeatherClient()
    with app_client(provider) as client:
        session_id = client.post("/sessions").json()["session_id"]
        missing_context = client.get(f"/sessions/{session_id}/weather")
        missing_session = client.get(f"/sessions/{uuid7()}/weather")

    assert missing_context.status_code == 404
    assert missing_context.json() == {
        "detail": {
            "code": "SESSION_CONTEXT_NOT_FOUND",
            "message": "Session context not found",
        }
    }
    assert missing_session.status_code == 404
    assert missing_session.json() == {
        "detail": {"code": "SESSION_NOT_FOUND", "message": "Session not found"}
    }
    assert provider.calls == []


def test_provider_failures_have_stable_sanitized_http_errors() -> None:
    provider = FakeWeatherClient(
        {"SBGR": AviationWeatherContractError("secret provider body")}
    )
    with app_client(provider) as client:
        session_id = create_session_with_context(
            client, {"departure_icao": "SBGR"}
        )
        upstream = client.get(f"/sessions/{session_id}/weather")

        provider.results["SBGR"] = AviationWeatherUnavailableError("secret URL")
        unavailable = client.get(f"/sessions/{session_id}/weather")

    assert upstream.status_code == 502
    assert upstream.json() == {
        "detail": {
            "code": "AVIATION_WEATHER_UPSTREAM_ERROR",
            "message": "Aviation weather service returned an invalid response",
        }
    }
    assert unavailable.status_code == 503
    assert unavailable.json() == {
        "detail": {
            "code": "AVIATION_WEATHER_UNAVAILABLE",
            "message": "Aviation weather service is temporarily unavailable",
        }
    }


def test_malformed_uuid_is_422_and_openapi_contains_weather_get() -> None:
    with app_client(FakeWeatherClient()) as client:
        malformed = client.get("/sessions/not-a-uuid/weather")
        schema = client.get("/openapi.json").json()

    assert malformed.status_code == 422
    assert "get" in schema["paths"]["/sessions/{session_id}/weather"]
