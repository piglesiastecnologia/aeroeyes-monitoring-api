from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.main import create_app
from aeroeyes_monitoring_api.persistence.models import (
    AttentionEventRecord,
    MonitoringSessionRecord,
)


def event_body(occurred_at: str, event_id: UUID) -> dict[str, object]:
    return {
        "event_id": str(event_id),
        "occurred_at": occurred_at,
        "state": "ATTENTION",
        "severity": "MEDIUM",
        "face_detected": True,
        "eye_state": "CLOSED",
        "closed_duration_ms": 1250,
        "schema_version": 1,
    }


def test_postgres_runtime_persists_http_lifecycle_across_app_instances(
    test_database_url: str,
    postgres_engine: Engine,
) -> None:
    first_app = create_app(database_url=test_database_url)
    second_app = create_app(database_url=test_database_url)
    disposed_engines: list[Engine] = []

    for app in (first_app, second_app):
        engine = app.state.database_engine
        event.listen(
            engine,
            "engine_disposed",
            lambda disposed, target=engine: disposed_engines.append(target),
        )

    event_id = uuid7()

    with TestClient(first_app) as first, TestClient(second_app) as second:
        created_response = first.post("/sessions")
        assert created_response.status_code == 201
        created = created_response.json()
        session_id = created["session_id"]

        observed_response = second.get(f"/sessions/{session_id}")
        assert observed_response.status_code == 200
        assert observed_response.json() == created

        body = event_body(created["started_at"], event_id)
        event_path = f"/sessions/{session_id}/events"
        ingested_response = first.post(event_path, json=body)
        assert ingested_response.status_code == 201
        assert ingested_response.json()["status"] == "created"

        replay_response = second.post(event_path, json=body)
        assert replay_response.status_code == 200
        assert replay_response.json()["status"] == "already_processed"
        assert replay_response.json()["event"] == ingested_response.json()["event"]

        completed_response = second.post(f"/sessions/{session_id}/complete")
        assert completed_response.status_code == 200
        completed = completed_response.json()
        assert completed["status"] == "COMPLETED"

    assert len(disposed_engines) == 2
    assert set(disposed_engines) == {
        first_app.state.database_engine,
        second_app.state.database_engine,
    }

    fresh_app = create_app(database_url=test_database_url)
    fresh_engine = fresh_app.state.database_engine
    fresh_disposed: list[Engine] = []
    event.listen(
        fresh_engine,
        "engine_disposed",
        lambda disposed: fresh_disposed.append(disposed),
    )

    with TestClient(fresh_app) as fresh:
        persisted_response = fresh.get(f"/sessions/{session_id}")
        assert persisted_response.status_code == 200
        assert persisted_response.json() == completed

        persisted_replay = fresh.post(event_path, json=body)
        assert persisted_replay.status_code == 200
        assert persisted_replay.json()["status"] == "already_processed"
        assert persisted_replay.json()["event"] == ingested_response.json()["event"]

    assert fresh_disposed == [fresh_engine]

    with Session(postgres_engine) as verification:
        assert verification.scalar(
            select(func.count()).select_from(MonitoringSessionRecord)
        ) == 1
        assert verification.scalar(
            select(func.count()).select_from(AttentionEventRecord)
        ) == 1
