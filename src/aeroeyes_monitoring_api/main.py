from fastapi import FastAPI

from aeroeyes_monitoring_api.api.events import create_events_router
from aeroeyes_monitoring_api.api.health import router as health_router
from aeroeyes_monitoring_api.api.sessions import create_sessions_router
from aeroeyes_monitoring_api.event_ingestion_service import EventIngestionService
from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.session_service import SessionService
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork

session_repository = InMemorySessionRepository()
session_service = SessionService(session_repository)
event_repository = InMemoryEventRepository()
event_ingestion_service = EventIngestionService(
    lambda: InMemoryUnitOfWork(session_repository, event_repository),
)

app = FastAPI(
    title="AeroEyes Monitoring API",
    description="Monitoring API for the AeroEyes Distributed Monitoring Platform.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(create_sessions_router(session_service))
app.include_router(create_events_router(event_ingestion_service))
