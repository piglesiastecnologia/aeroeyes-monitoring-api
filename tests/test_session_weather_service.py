from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from aeroeyes_monitoring_api.aviation_weather_client import (
    AviationWeatherContractError,
    AviationWeatherRateLimitError,
    AviationWeatherRequestError,
    AviationWeatherUnavailableError,
)
from aeroeyes_monitoring_api.domain.metar import (
    FlightCategory,
    MetarObservation,
    MetarReportType,
)
from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)
from aeroeyes_monitoring_api.session_context_service import (
    SessionContextNotFoundError,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.session_weather_service import (
    SessionWeatherService,
    SessionWeatherUnavailableError,
    SessionWeatherUpstreamError,
)
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork


SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
MISSING_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000099")
STARTED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def observation(station_icao: str = "SBGR") -> MetarObservation:
    return MetarObservation(
        station_icao=station_icao,
        report_type=MetarReportType.METAR,
        observed_at=datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc),
        raw_text=f"METAR {station_icao} 081230Z",
        flight_category=FlightCategory.VFR,
        temperature_c=24.0,
        dewpoint_c=15.0,
        wind_direction_deg=90,
        wind_speed_kt=8.0,
        visibility_sm=10.0,
        visibility_greater_than=True,
        ceiling_ft_agl=5000,
        altimeter_hpa=1018.0,
    )


class FakeWeatherClient:
    def __init__(self, results: dict[str, object] | None = None) -> None:
        self.results = results or {}
        self.calls: list[str] = []
        self.before_call = lambda: None

    def get_metar(self, station_icao: str) -> MetarObservation | None:
        self.before_call()
        self.calls.append(station_icao)
        result = self.results.get(station_icao)
        if isinstance(result, Exception):
            raise result
        assert result is None or isinstance(result, MetarObservation)
        return result


class RecordingUnitOfWork(InMemoryUnitOfWork):
    def __init__(self, sessions, contexts) -> None:
        super().__init__(sessions, InMemoryEventRepository(), contexts)
        self.commit_count = 0
        self.exited = False

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        super().__exit__(exc_type, exc_value, traceback)
        self.exited = True

    def commit(self) -> None:
        self.commit_count += 1


def service_fixture(
    *,
    status: SessionStatus | None = SessionStatus.ACTIVE,
    departure_icao: str | None = "SBGR",
    destination_icao: str | None = "SBRJ",
    include_context: bool = True,
    provider_results: dict[str, object] | None = None,
) -> tuple[SessionWeatherService, FakeWeatherClient, list[RecordingUnitOfWork]]:
    sessions = InMemorySessionRepository()
    contexts = InMemorySessionContextRepository()
    if status is not None:
        sessions.add(
            MonitoringSession(
                session_id=SESSION_ID,
                status=status,
                started_at=STARTED_AT,
                ended_at=(
                    STARTED_AT + timedelta(minutes=30)
                    if status is SessionStatus.COMPLETED
                    else None
                ),
            )
        )
    if include_context:
        contexts.save(
            SessionContext(
                session_id=SESSION_ID,
                departure_icao=departure_icao,
                destination_icao=destination_icao,
            )
        )

    provider = FakeWeatherClient(provider_results)
    created_uows: list[RecordingUnitOfWork] = []

    def uow_factory() -> RecordingUnitOfWork:
        uow = RecordingUnitOfWork(sessions, contexts)
        created_uows.append(uow)
        return uow

    return SessionWeatherService(uow_factory, provider), provider, created_uows


def test_missing_session_and_context_do_not_call_provider() -> None:
    missing_session_service, missing_session_provider, missing_session_uows = (
        service_fixture(status=None, include_context=False)
    )
    with pytest.raises(SessionNotFoundError):
        missing_session_service.get_weather(MISSING_SESSION_ID)
    assert missing_session_provider.calls == []
    assert missing_session_uows[0].commit_count == 0

    missing_context_service, missing_context_provider, missing_context_uows = (
        service_fixture(include_context=False)
    )
    with pytest.raises(SessionContextNotFoundError):
        missing_context_service.get_weather(SESSION_ID)
    assert missing_context_provider.calls == []
    assert missing_context_uows[0].commit_count == 0


def test_all_null_context_returns_empty_slots_without_provider_or_commit() -> None:
    service, provider, uows = service_fixture(
        departure_icao=None,
        destination_icao=None,
    )

    weather = service.get_weather(SESSION_ID)

    assert weather.session_id == SESSION_ID
    assert weather.departure is None
    assert weather.destination is None
    assert provider.calls == []
    assert uows[0].commit_count == 0


@pytest.mark.parametrize(
    ("departure_icao", "destination_icao", "expected_slot"),
    [("SBGR", None, "departure"), (None, "SBRJ", "destination")],
)
def test_single_configured_icao_is_queried_once(
    departure_icao: str | None,
    destination_icao: str | None,
    expected_slot: str,
) -> None:
    station = departure_icao or destination_icao
    assert station is not None
    expected = observation(station)
    service, provider, _ = service_fixture(
        departure_icao=departure_icao,
        destination_icao=destination_icao,
        provider_results={station: expected},
    )

    weather = service.get_weather(SESSION_ID)

    assert provider.calls == [station]
    slot = getattr(weather, expected_slot)
    assert slot is not None
    assert slot.station_icao == station
    assert slot.observation is expected
    other_slot = "destination" if expected_slot == "departure" else "departure"
    assert getattr(weather, other_slot) is None


def test_distinct_icaos_are_queried_once_each_and_observations_are_preserved() -> None:
    sbgr = observation("SBGR")
    sbrj = observation("SBRJ")
    service, provider, uows = service_fixture(
        provider_results={"SBGR": sbgr, "SBRJ": sbrj},
    )

    weather = service.get_weather(SESSION_ID)

    assert provider.calls == ["SBGR", "SBRJ"]
    assert weather.departure is not None
    assert weather.departure.observation is sbgr
    assert weather.destination is not None
    assert weather.destination.observation is sbrj
    assert uows[0].commit_count == 0


@pytest.mark.parametrize("provider_result", [observation("SBGR"), None])
def test_duplicate_icao_is_queried_once_and_reused(provider_result) -> None:
    service, provider, _ = service_fixture(
        departure_icao="SBGR",
        destination_icao="SBGR",
        provider_results={"SBGR": provider_result},
    )

    weather = service.get_weather(SESSION_ID)

    assert provider.calls == ["SBGR"]
    assert weather.departure is not None
    assert weather.destination is not None
    assert weather.departure.observation is provider_result
    assert weather.destination.observation is provider_result


def test_provider_no_data_keeps_configured_airport_with_null_observation() -> None:
    service, provider, _ = service_fixture(destination_icao=None)

    weather = service.get_weather(SESSION_ID)

    assert provider.calls == ["SBGR"]
    assert weather.departure is not None
    assert weather.departure.station_icao == "SBGR"
    assert weather.departure.observation is None


@pytest.mark.parametrize("status", [SessionStatus.ACTIVE, SessionStatus.COMPLETED])
def test_active_and_completed_sessions_are_accepted(status: SessionStatus) -> None:
    service, provider, _ = service_fixture(
        status=status,
        departure_icao=None,
        destination_icao=None,
    )

    assert service.get_weather(SESSION_ID).session_id == SESSION_ID
    assert provider.calls == []


@pytest.mark.parametrize(
    "provider_error",
    [AviationWeatherRateLimitError(), AviationWeatherUnavailableError()],
)
def test_transient_provider_failures_are_translated(provider_error: Exception) -> None:
    service, _, _ = service_fixture(
        destination_icao=None,
        provider_results={"SBGR": provider_error},
    )

    with pytest.raises(SessionWeatherUnavailableError) as raised:
        service.get_weather(SESSION_ID)

    assert raised.value.__cause__ is provider_error


@pytest.mark.parametrize(
    "provider_error",
    [AviationWeatherRequestError(), AviationWeatherContractError()],
)
def test_invalid_provider_failures_are_translated(provider_error: Exception) -> None:
    service, _, _ = service_fixture(
        destination_icao=None,
        provider_results={"SBGR": provider_error},
    )

    with pytest.raises(SessionWeatherUpstreamError) as raised:
        service.get_weather(SESSION_ID)

    assert raised.value.__cause__ is provider_error


def test_provider_access_starts_only_after_uow_exit() -> None:
    service, provider, uows = service_fixture(destination_icao=None)
    provider.before_call = lambda: (
        None if uows and uows[-1].exited else pytest.fail("UoW still active")
    )

    service.get_weather(SESSION_ID)

    assert uows[0].exited
    assert uows[0].commit_count == 0


def test_second_station_failure_fails_the_whole_request() -> None:
    service, provider, _ = service_fixture(
        provider_results={
            "SBGR": observation("SBGR"),
            "SBRJ": AviationWeatherUnavailableError(),
        },
    )

    with pytest.raises(SessionWeatherUnavailableError):
        service.get_weather(SESSION_ID)

    assert provider.calls == ["SBGR", "SBRJ"]
