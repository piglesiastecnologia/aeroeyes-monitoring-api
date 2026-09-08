from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from aeroeyes_monitoring_api.domain.metar import FlightCategory, MetarReportType
from aeroeyes_monitoring_api.domain.session_weather import SessionWeather
from aeroeyes_monitoring_api.session_context_service import (
    SessionContextNotFoundError,
)
from aeroeyes_monitoring_api.session_service import SessionNotFoundError
from aeroeyes_monitoring_api.session_weather_service import (
    SessionWeatherService,
    SessionWeatherUnavailableError,
    SessionWeatherUpstreamError,
)


class MetarObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    station_icao: str
    report_type: MetarReportType
    observed_at: datetime
    raw_text: str
    flight_category: FlightCategory | None
    temperature_c: float | None
    dewpoint_c: float | None
    wind_direction_deg: int | None
    wind_variable: bool
    wind_speed_kt: float | None
    wind_gust_kt: float | None
    visibility_sm: float | None
    visibility_greater_than: bool
    weather: str | None
    ceiling_ft_agl: int | None
    altimeter_hpa: float | None


class AirportWeatherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    station_icao: str
    observation: MetarObservationResponse | None


class SessionWeatherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    departure: AirportWeatherResponse | None
    destination: AirportWeatherResponse | None


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def create_weather_router(service: SessionWeatherService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/sessions/{session_id}/weather",
        response_model=SessionWeatherResponse,
        summary="Get current weather for a session route",
        description=(
            "Returns current, non-historical METAR context for the departure "
            "and destination airports configured on the monitoring session."
        ),
    )
    def get_weather(session_id: UUID) -> SessionWeather:
        try:
            return service.get_weather(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_detail("SESSION_NOT_FOUND", "Session not found"),
            ) from error
        except SessionContextNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_detail(
                    "SESSION_CONTEXT_NOT_FOUND",
                    "Session context not found",
                ),
            ) from error
        except SessionWeatherUpstreamError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_error_detail(
                    "AVIATION_WEATHER_UPSTREAM_ERROR",
                    "Aviation weather service returned an invalid response",
                ),
            ) from error
        except SessionWeatherUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_error_detail(
                    "AVIATION_WEATHER_UNAVAILABLE",
                    "Aviation weather service is temporarily unavailable",
                ),
            ) from error

    return router
