from fastapi import FastAPI

from aeroeyes_monitoring_api.api.health import router as health_router
from aeroeyes_monitoring_api.api.sessions import create_sessions_router
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import SessionService

session_repository = InMemorySessionRepository()
session_service = SessionService(session_repository)

app = FastAPI(
    title="AeroEyes Monitoring API",
    description="Monitoring API for the AeroEyes Distributed Monitoring Platform.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(create_sessions_router(session_service))
