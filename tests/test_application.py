import os
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import aeroeyes_monitoring_api.main as application


def test_importing_application_factory_does_not_require_database_url() -> None:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from aeroeyes_monitoring_api.main import create_app",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_default_composition_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        application.create_app()


def test_default_composition_creates_one_engine_and_disposes_it(monkeypatch) -> None:
    database_url = "postgresql+psycopg://runtime.example/aeroeyes"
    created_for: list[str] = []

    class EngineSpy:
        disposed = False

        def dispose(self) -> None:
            self.disposed = True

    engine = EngineSpy()
    session_factories_for: list[EngineSpy] = []

    monkeypatch.setattr(
        application,
        "database_url_from_env",
        lambda: database_url,
    )

    def create_engine(url: str) -> EngineSpy:
        created_for.append(url)
        return engine

    monkeypatch.setattr(application, "create_database_engine", create_engine)

    def create_session_factory(actual_engine: EngineSpy):
        session_factories_for.append(actual_engine)
        return lambda: None

    monkeypatch.setattr(application, "create_session_factory", create_session_factory)

    app = application.create_app()

    assert created_for == [database_url]
    assert session_factories_for == [engine]
    assert app.state.database_engine is engine
    assert not engine.disposed

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        assert created_for == [database_url]

    assert engine.disposed


def test_create_app_preserves_openapi_and_swagger_routes(app: FastAPI) -> None:
    assert set(app.openapi()["paths"]) == {
        "/health",
        "/sessions",
        "/sessions/{session_id}",
        "/sessions/{session_id}/complete",
        "/sessions/{session_id}/events",
        "/sessions/{session_id}/context",
    }
    assert {getattr(route, "path", None) for route in app.routes} >= {
        "/docs",
        "/openapi.json",
    }


def test_create_app_rejects_ambiguous_persistence_composition() -> None:
    with pytest.raises(
        ValueError,
        match="database_url and unit_of_work_factory cannot be provided together",
    ):
        application.create_app(
            database_url="postgresql+psycopg://runtime.example/aeroeyes",
            unit_of_work_factory=lambda: None,
        )
