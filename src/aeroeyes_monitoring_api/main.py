from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from aeroeyes_monitoring_api.api.attention_states import (
    create_attention_states_router,
)
from aeroeyes_monitoring_api.api.events import create_events_router
from aeroeyes_monitoring_api.api.health import router as health_router
from aeroeyes_monitoring_api.api.session_contexts import (
    create_session_contexts_router,
)
from aeroeyes_monitoring_api.api.sessions import create_sessions_router
from aeroeyes_monitoring_api.api.weather import create_weather_router
from aeroeyes_monitoring_api.aviation_weather_client import AviationWeatherClient
from aeroeyes_monitoring_api.config import cors_allowed_origins_from_env
from aeroeyes_monitoring_api.event_ingestion_service import EventIngestionService
from aeroeyes_monitoring_api.persistence.database import (
    create_database_engine,
    create_session_factory,
    database_url_from_env,
)
from aeroeyes_monitoring_api.persistence.postgres_unit_of_work import (
    PostgresUnitOfWork,
)
from aeroeyes_monitoring_api.session_attention_state_service import (
    SessionAttentionStateService,
)
from aeroeyes_monitoring_api.session_context_service import SessionContextService
from aeroeyes_monitoring_api.session_service import SessionService
from aeroeyes_monitoring_api.session_weather_service import SessionWeatherService
from aeroeyes_monitoring_api.unit_of_work import UnitOfWork


AVIATION_WEATHER_TIMEOUT_SECONDS = 5.0


def create_app(
    *,
    database_url: str | None = None,
    unit_of_work_factory: Callable[[], UnitOfWork] | None = None,
    cors_allowed_origins: Sequence[str] | None = None,
    aviation_weather_client: AviationWeatherClient | None = None,
) -> FastAPI:
    if database_url is not None and unit_of_work_factory is not None:
        raise ValueError(
            "database_url and unit_of_work_factory cannot be provided together"
        )

    engine: Engine | None = None
    if unit_of_work_factory is None:
        resolved_database_url = (
            database_url if database_url is not None else database_url_from_env()
        )
        engine = create_database_engine(resolved_database_url)
        session_factory = create_session_factory(engine)
        unit_of_work_factory = lambda: PostgresUnitOfWork(session_factory)

    owned_aviation_weather_http_client: httpx.Client | None = None
    if aviation_weather_client is None:
        owned_aviation_weather_http_client = httpx.Client(
            timeout=AVIATION_WEATHER_TIMEOUT_SECONDS,
        )
        aviation_weather_client = AviationWeatherClient(
            owned_aviation_weather_http_client,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            try:
                if owned_aviation_weather_http_client is not None:
                    owned_aviation_weather_http_client.close()
            finally:
                if engine is not None:
                    engine.dispose()

    app = FastAPI(
        title="AeroEyes Monitoring API",
        description="Monitoring API for the AeroEyes Distributed Monitoring Platform.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.database_engine = engine
    app.state.aviation_weather_client = aviation_weather_client

    resolved_cors_allowed_origins = (
        cors_allowed_origins_from_env()
        if cors_allowed_origins is None
        else cors_allowed_origins
    )
    if resolved_cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    session_service = SessionService(unit_of_work_factory)
    event_ingestion_service = EventIngestionService(unit_of_work_factory)
    session_attention_state_service = SessionAttentionStateService(
        unit_of_work_factory
    )
    session_context_service = SessionContextService(unit_of_work_factory)
    session_weather_service = SessionWeatherService(
        unit_of_work_factory,
        aviation_weather_client,
    )

    app.include_router(health_router)
    app.include_router(create_sessions_router(session_service))
    app.include_router(create_events_router(event_ingestion_service))
    app.include_router(
        create_attention_states_router(session_attention_state_service)
    )
    app.include_router(create_session_contexts_router(session_context_service))
    app.include_router(create_weather_router(session_weather_service))
    return app
