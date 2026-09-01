import pytest
from fastapi import FastAPI

from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.main import create_app
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork


@pytest.fixture
def app() -> FastAPI:
    sessions = InMemorySessionRepository()
    events = InMemoryEventRepository()
    return create_app(
        unit_of_work_factory=lambda: InMemoryUnitOfWork(sessions, events),
    )
