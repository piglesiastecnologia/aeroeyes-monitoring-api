from fastapi.testclient import TestClient

from aeroeyes_monitoring_api.main import create_app


class NoObservationWeatherClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_metar(self, station_icao: str) -> None:
        self.calls.append(station_icao)
        return None


def test_postgres_backed_session_weather_uses_persisted_route(
    test_database_url: str,
) -> None:
    provider = NoObservationWeatherClient()
    app = create_app(
        database_url=test_database_url,
        aviation_weather_client=provider,
    )

    with TestClient(app) as client:
        session_response = client.post("/sessions")
        assert session_response.status_code == 201
        session_id = session_response.json()["session_id"]

        context_response = client.put(
            f"/sessions/{session_id}/context",
            json={
                "flight_number": "AE006B",
                "departure_icao": "SBGR",
                "destination_icao": "SBRJ",
            },
        )
        assert context_response.status_code == 200

        weather_response = client.get(f"/sessions/{session_id}/weather")

    assert weather_response.status_code == 200
    assert weather_response.json() == {
        "session_id": session_id,
        "departure": {"station_icao": "SBGR", "observation": None},
        "destination": {"station_icao": "SBRJ", "observation": None},
    }
    assert provider.calls == ["SBGR", "SBRJ"]
