from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aeroeyes_monitoring_api.domain.identity import uuid7


def event_body(
    event_id: str,
    occurred_at: datetime,
    *,
    state: str = "NORMAL",
    severity: str = "INFO",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "occurred_at": occurred_at.isoformat(),
        "state": state,
        "severity": severity,
        "face_detected": True,
        "eye_state": "OPEN",
        "closed_duration_ms": 0,
        "schema_version": 1,
    }


def test_existing_session_without_events_returns_no_data(app: FastAPI) -> None:
    with TestClient(app) as client:
        session = client.post("/sessions").json()
        response = client.get(
            f"/sessions/{session['session_id']}/attention-state"
        )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session["session_id"],
        "availability": "NO_DATA",
        "latest_event": None,
    }


def test_latest_semantic_event_is_returned_with_ingestion_metadata(
    app: FastAPI,
) -> None:
    later_event_id = "01890f3d-2d00-7000-8000-000000000020"
    older_event_id = "01890f3d-2d00-7000-8000-000000000010"
    with TestClient(app) as client:
        session = client.post("/sessions").json()
        started_at = datetime.fromisoformat(session["started_at"])
        events_path = f"/sessions/{session['session_id']}/events"
        later = event_body(
            later_event_id,
            started_at + timedelta(seconds=2),
            state="ATTENTION",
            severity="MEDIUM",
        )
        older = event_body(
            older_event_id,
            started_at + timedelta(seconds=1),
        )
        assert client.post(events_path, json=later).status_code == 201
        assert client.post(events_path, json=older).status_code == 201

        response = client.get(
            f"/sessions/{session['session_id']}/attention-state"
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["session_id"] == session["session_id"]
    assert payload["availability"] == "AVAILABLE"
    assert payload["latest_event"]["event_id"] == later_event_id
    assert payload["latest_event"]["session_id"] == session["session_id"]
    assert payload["latest_event"]["state"] == "ATTENTION"
    assert payload["latest_event"]["received_at"] is not None


def test_attention_state_isolated_by_session(app: FastAPI) -> None:
    with TestClient(app) as client:
        first = client.post("/sessions").json()
        second = client.post("/sessions").json()
        occurred_at = datetime.fromisoformat(first["started_at"])
        created = client.post(
            f"/sessions/{first['session_id']}/events",
            json=event_body(str(uuid7()), occurred_at),
        )
        second_response = client.get(
            f"/sessions/{second['session_id']}/attention-state"
        )

    assert created.status_code == 201
    assert second_response.status_code == 200
    assert second_response.json()["availability"] == "NO_DATA"
    assert second_response.json()["latest_event"] is None


def test_recent_events_are_limited_and_newest_first(app: FastAPI) -> None:
    event_ids = (
        "01890f3d-2d00-7000-8000-000000000010",
        "01890f3d-2d00-7000-8000-000000000020",
        "01890f3d-2d00-7000-8000-000000000030",
    )
    with TestClient(app) as client:
        session = client.post("/sessions").json()
        started_at = datetime.fromisoformat(session["started_at"])
        events_path = f"/sessions/{session['session_id']}/events"
        for offset, event_id in enumerate(event_ids, start=1):
            response = client.post(
                events_path,
                json=event_body(
                    event_id,
                    started_at + timedelta(seconds=offset),
                ),
            )
            assert response.status_code == 201

        response = client.get(f"{events_path}?limit=2")

    assert response.status_code == 200
    assert response.json()["session_id"] == session["session_id"]
    assert [event["event_id"] for event in response.json()["events"]] == [
        event_ids[2],
        event_ids[1],
    ]


def test_recent_events_preserve_empty_and_not_found_semantics(
    app: FastAPI,
) -> None:
    with TestClient(app) as client:
        session = client.post("/sessions").json()
        empty = client.get(f"/sessions/{session['session_id']}/events")
        missing = client.get(f"/sessions/{uuid7()}/events")
        invalid_limit = client.get(
            f"/sessions/{session['session_id']}/events?limit=51"
        )

    assert empty.status_code == 200
    assert empty.json() == {
        "session_id": session["session_id"],
        "events": [],
    }
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "SESSION_NOT_FOUND"
    assert invalid_limit.status_code == 422


def test_unknown_session_returns_structured_not_found(app: FastAPI) -> None:
    missing_session_id = uuid7()

    with TestClient(app) as client:
        response = client.get(
            f"/sessions/{missing_session_id}/attention-state"
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "SESSION_NOT_FOUND",
            "message": "Session not found",
        }
    }


def test_malformed_session_id_is_rejected_and_route_is_documented(
    app: FastAPI,
) -> None:
    with TestClient(app) as client:
        malformed = client.get("/sessions/not-a-uuid/attention-state")
        schema = client.get("/openapi.json").json()

    assert malformed.status_code == 422
    assert "get" in schema["paths"]["/sessions/{session_id}/attention-state"]
    assert "get" in schema["paths"]["/sessions/{session_id}/events"]
