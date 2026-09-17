from collections.abc import Callable
from uuid import UUID

from aeroeyes_monitoring_api.aviation_weather_client import (
    AviationWeatherClient,
    AviationWeatherContractError,
    AviationWeatherRateLimitError,
    AviationWeatherRequestError,
    AviationWeatherUnavailableError,
)
from aeroeyes_monitoring_api.domain.metar import MetarObservation
from aeroeyes_monitoring_api.domain.session_weather import (
    AirportWeather,
    SessionWeather,
)
from aeroeyes_monitoring_api.session_context_service import (
    SessionContextNotFoundError,
)
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.unit_of_work import UnitOfWork


class SessionWeatherUnavailableError(RuntimeError):
    """The weather provider is temporarily unavailable."""


class SessionWeatherUpstreamError(RuntimeError):
    """The weather provider request or response was invalid."""


class SessionWeatherService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        aviation_weather_client: AviationWeatherClient,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._aviation_weather_client = aviation_weather_client

    def get_weather(self, session_id: UUID) -> SessionWeather:
        with self._unit_of_work_factory() as uow:
            if uow.sessions.get(session_id) is None:
                raise SessionNotFoundError(session_id)

            context = uow.contexts.get(session_id)
            if context is None:
                raise SessionContextNotFoundError(session_id)

            departure_icao = context.departure_icao
            destination_icao = context.destination_icao

        observations: dict[str, MetarObservation | None] = {}
        for station_icao in (departure_icao, destination_icao):
            if station_icao is None or station_icao in observations:
                continue
            observations[station_icao] = self._get_metar(station_icao)

        return SessionWeather(
            session_id=session_id,
            departure=(
                AirportWeather(
                    station_icao=departure_icao,
                    observation=observations[departure_icao],
                )
                if departure_icao is not None
                else None
            ),
            destination=(
                AirportWeather(
                    station_icao=destination_icao,
                    observation=observations[destination_icao],
                )
                if destination_icao is not None
                else None
            ),
        )

    def _get_metar(self, station_icao: str) -> MetarObservation | None:
        try:
            return self._aviation_weather_client.get_metar(station_icao)
        except (
            AviationWeatherRateLimitError,
            AviationWeatherUnavailableError,
        ) as error:
            raise SessionWeatherUnavailableError from error
        except (
            AviationWeatherRequestError,
            AviationWeatherContractError,
        ) as error:
            raise SessionWeatherUpstreamError from error
