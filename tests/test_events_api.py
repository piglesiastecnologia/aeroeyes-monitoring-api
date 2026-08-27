import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.main import app


def valid_body(occurred_at: str) -> dict[str, object]:
    return {
        "event_id": str(uuid7()),
        "occurred_at": occurred_at,
        "state": "ATTENTION",
        "severity": "MEDIUM",
        "face_detected": True,
        "eye_state": "CLOSED",
        "closed_duration_ms": 1250,
        "schema_version": 1,
    }


def test_create_replay_and_changed_payload_conflict() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session_response = await client.post("/sessions")
            session = session_response.json()
            body = valid_body(session["started_at"])
            path = f"/sessions/{session['session_id']}/events"

            created_response = await client.post(path, json=body)
            replay_response = await client.post(path, json=body)
            changed = {**body, "state": "CRITICAL"}
            conflict_response = await client.post(path, json=changed)

        assert created_response.status_code == 201
        assert "location" not in created_response.headers
        assert created_response.json()["status"] == "created"
        assert created_response.json()["event"]["session_id"] == session["session_id"]
        assert "received_at" in created_response.json()["event"]

        assert replay_response.status_code == 200
        assert replay_response.json()["status"] == "already_processed"
        assert replay_response.json()["event"] == created_response.json()["event"]

        assert conflict_response.status_code == 409
        assert conflict_response.json()["detail"]["code"] == "EVENT_ID_CONFLICT"

    asyncio.run(exercise())


def test_same_event_id_in_another_existing_session_conflicts() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first = (await client.post("/sessions")).json()
            second = (await client.post("/sessions")).json()
            body = valid_body(second["started_at"])

            first_response = await client.post(
                f"/sessions/{first['session_id']}/events",
                json=body,
            )
            second_response = await client.post(
                f"/sessions/{second['session_id']}/events",
                json=body,
            )

        assert first_response.status_code == 201
        assert second_response.status_code == 409
        assert second_response.json()["detail"]["code"] == "EVENT_ID_CONFLICT"

    asyncio.run(exercise())


def test_unknown_and_malformed_sessions_are_rejected() -> None:
    async def exercise() -> None:
        body = valid_body(datetime.now(timezone.utc).isoformat())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            unknown = await client.post(f"/sessions/{uuid7()}/events", json=body)
            malformed = await client.post("/sessions/not-a-uuid/events", json=body)

        assert unknown.status_code == 404
        assert unknown.json()["detail"]["code"] == "SESSION_NOT_FOUND"
        assert malformed.status_code == 422

    asyncio.run(exercise())


def invalid_body(case: str, occurred_at: str, session_id: str) -> dict[str, object]:
    body = valid_body(occurred_at)
    if case.startswith("missing_"):
        del body[case.removeprefix("missing_")]
    elif case == "extra_field":
        body["device"] = "camera-1"
    elif case == "session_id":
        body["session_id"] = session_id
    elif case == "received_at":
        body["received_at"] = occurred_at
    elif case == "message":
        body["message"] = "Attention warning"
    elif case == "reason":
        body["reason"] = "eyes closed"
    elif case == "string_boolean":
        body["face_detected"] = "true"
    elif case == "string_duration":
        body["closed_duration_ms"] = "1250"
    elif case == "float_duration":
        body["closed_duration_ms"] = 1250.0
    elif case == "float_schema_version":
        body["schema_version"] = 1.0
    elif case == "invalid_enum":
        body["eye_state"] = "BLINK_DETECTED"
    elif case == "malformed_event_id":
        body["event_id"] = "not-a-uuid"
    elif case == "non_uuid7_event_id":
        body["event_id"] = str(uuid4())
    elif case == "non_utc_occurred_at":
        body["occurred_at"] = "2026-08-27T09:00:00-03:00"
    elif case == "numeric_occurred_at":
        body["occurred_at"] = 1787832000
    return body


@pytest.mark.parametrize(
    "case",
    [
        "missing_eye_state",
        "missing_closed_duration_ms",
        "missing_schema_version",
        "extra_field",
        "session_id",
        "received_at",
        "message",
        "reason",
        "string_boolean",
        "string_duration",
        "float_duration",
        "float_schema_version",
        "invalid_enum",
        "malformed_event_id",
        "non_uuid7_event_id",
        "non_utc_occurred_at",
        "numeric_occurred_at",
    ],
)
def test_invalid_request_contract_is_rejected(case: str) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session = (await client.post("/sessions")).json()
            body = invalid_body(case, session["started_at"], session["session_id"])
            response = await client.post(
                f"/sessions/{session['session_id']}/events",
                json=body,
            )

        assert response.status_code == 422

    asyncio.run(exercise())


def test_explicit_null_eye_fields_are_accepted() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session = (await client.post("/sessions")).json()
            body = valid_body(session["started_at"])
            body["eye_state"] = None
            body["closed_duration_ms"] = None
            response = await client.post(
                f"/sessions/{session['session_id']}/events",
                json=body,
            )

        assert response.status_code == 201
        assert response.json()["event"]["eye_state"] is None
        assert response.json()["event"]["closed_duration_ms"] is None

    asyncio.run(exercise())


def test_unsupported_schema_version_has_stable_error_code() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session = (await client.post("/sessions")).json()
            body = valid_body(session["started_at"])
            body["schema_version"] = 2
            response = await client.post(
                f"/sessions/{session['session_id']}/events",
                json=body,
            )

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "UNSUPPORTED_SCHEMA_VERSION"

    asyncio.run(exercise())


def test_event_before_session_is_rejected() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session = (await client.post("/sessions")).json()
            started_at = datetime.fromisoformat(
                session["started_at"].replace("Z", "+00:00")
            )
            body = valid_body((started_at - timedelta(microseconds=1)).isoformat())
            response = await client.post(
                f"/sessions/{session['session_id']}/events",
                json=body,
            )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "EVENT_OUTSIDE_SESSION"

    asyncio.run(exercise())


def test_completed_session_accepts_valid_late_event() -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session = (await client.post("/sessions")).json()
            completed = await client.post(
                f"/sessions/{session['session_id']}/complete"
            )
            response = await client.post(
                f"/sessions/{session['session_id']}/events",
                json=valid_body(session["started_at"]),
            )

        assert completed.status_code == 200
        assert response.status_code == 201
        assert response.json()["status"] == "created"

    asyncio.run(exercise())
