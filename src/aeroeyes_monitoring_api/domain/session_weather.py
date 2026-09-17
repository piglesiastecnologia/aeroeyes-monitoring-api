from dataclasses import dataclass
from uuid import UUID

from aeroeyes_monitoring_api.domain.metar import MetarObservation


@dataclass(frozen=True, slots=True)
class AirportWeather:
    station_icao: str
    observation: MetarObservation | None


@dataclass(frozen=True, slots=True)
class SessionWeather:
    session_id: UUID
    departure: AirportWeather | None
    destination: AirportWeather | None
