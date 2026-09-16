from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.main import create_app


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    """Override create_all cleanup: this module runs on an Alembic-built schema."""
    yield


def test_attention_state_persists_across_application_instances(
    test_database_url: str,
) -> None:
    event_id = str(uuid7())
    with TestClient(create_app(database_url=test_database_url)) as first_client:
        session = first_client.post("/sessions").json()
        occurred_at = datetime.fromisoformat(session["started_at"]) + timedelta(
            seconds=1
        )
        event_response = first_client.post(
            f"/sessions/{session['session_id']}/events",
            json={
                "event_id": event_id,
                "occurred_at": occurred_at.isoformat(),
                "state": "NORMAL",
                "severity": "INFO",
                "face_detected": True,
                "eye_state": "OPEN",
                "closed_duration_ms": 0,
                "schema_version": 1,
            },
        )
        assert event_response.status_code == 201

    with TestClient(create_app(database_url=test_database_url)) as second_client:
        response = second_client.get(
            f"/sessions/{session['session_id']}/attention-state"
        )

    assert response.status_code == 200
    assert response.json()["availability"] == "AVAILABLE"
    assert response.json()["latest_event"]["event_id"] == event_id


def test_recent_events_persist_in_descending_semantic_order(
    test_database_url: str,
) -> None:
    event_ids = [str(uuid7()), str(uuid7()), str(uuid7())]
    with TestClient(create_app(database_url=test_database_url)) as first_client:
        session = first_client.post("/sessions").json()
        started_at = datetime.fromisoformat(session["started_at"])
        for offset, event_id in enumerate(event_ids, start=1):
            response = first_client.post(
                f"/sessions/{session['session_id']}/events",
                json={
                    "event_id": event_id,
                    "occurred_at": (
                        started_at + timedelta(seconds=offset)
                    ).isoformat(),
                    "state": "NORMAL",
                    "severity": "INFO",
                    "face_detected": True,
                    "eye_state": "OPEN",
                    "closed_duration_ms": 0,
                    "schema_version": 1,
                },
            )
            assert response.status_code == 201

    with TestClient(create_app(database_url=test_database_url)) as second_client:
        response = second_client.get(
            f"/sessions/{session['session_id']}/events?limit=2"
        )

    assert response.status_code == 200
    assert [event["event_id"] for event in response.json()["events"]] == [
        event_ids[2],
        event_ids[1],
    ]
