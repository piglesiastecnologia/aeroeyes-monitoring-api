import asyncio
from datetime import datetime, timedelta
from uuid import UUID

import httpx
from fastapi import FastAPI

from aeroeyes_monitoring_api.domain.identity import uuid7


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_session_lifecycle(app: FastAPI) -> None:
    async def exercise_lifecycle() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            created_response = await client.post("/sessions")
            assert created_response.status_code == 201
            created = created_response.json()

            session_id = UUID(created["session_id"])
            started_at = parse_timestamp(created["started_at"])
            assert session_id.version == 7
            assert created["status"] == "ACTIVE"
            assert started_at.utcoffset() == timedelta(0)
            assert created["ended_at"] is None
            assert created_response.headers["location"] == f"/sessions/{session_id}"

            active_response = await client.get(f"/sessions/{session_id}")
            assert active_response.status_code == 200
            assert active_response.json() == created

            completed_response = await client.post(
                f"/sessions/{session_id}/complete"
            )
            assert completed_response.status_code == 200
            completed = completed_response.json()
            ended_at = parse_timestamp(completed["ended_at"])
            assert completed["status"] == "COMPLETED"
            assert ended_at.utcoffset() == timedelta(0)
            assert ended_at >= started_at

            retrieved_response = await client.get(f"/sessions/{session_id}")
            assert retrieved_response.status_code == 200
            assert retrieved_response.json() == completed

            repeated_response = await client.post(
                f"/sessions/{session_id}/complete"
            )
            assert repeated_response.status_code == 200
            assert repeated_response.json()["ended_at"] == completed["ended_at"]

    asyncio.run(exercise_lifecycle())


def test_unknown_session_returns_404(app: FastAPI) -> None:
    async def request_unknown_session() -> None:
        session_id = uuid7()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            get_response = await client.get(f"/sessions/{session_id}")
            complete_response = await client.post(
                f"/sessions/{session_id}/complete"
            )

        assert get_response.status_code == 404
        assert get_response.json() == {"detail": "Session not found"}
        assert complete_response.status_code == 404
        assert complete_response.json() == {"detail": "Session not found"}

    asyncio.run(request_unknown_session())


def test_malformed_session_id_returns_422(app: FastAPI) -> None:
    async def request_malformed_session() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            get_response = await client.get("/sessions/not-a-uuid")
            complete_response = await client.post(
                "/sessions/not-a-uuid/complete"
            )

        assert get_response.status_code == 422
        assert complete_response.status_code == 422

    asyncio.run(request_malformed_session())
