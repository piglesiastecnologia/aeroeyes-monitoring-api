import asyncio
from collections.abc import Sequence

import httpx

from aeroeyes_monitoring_api.event_repository import InMemoryEventRepository
from aeroeyes_monitoring_api.main import create_app
from aeroeyes_monitoring_api.session_context_repository import (
    InMemorySessionContextRepository,
)
from aeroeyes_monitoring_api.session_repository import InMemorySessionRepository
from aeroeyes_monitoring_api.unit_of_work import InMemoryUnitOfWork

LOCALHOST_ORIGIN = "http://localhost:5173"
LOOPBACK_ORIGIN = "http://127.0.0.1:5173"


def create_in_memory_app(
    cors_allowed_origins: Sequence[str] | None,
):
    sessions = InMemorySessionRepository()
    events = InMemoryEventRepository()
    contexts = InMemorySessionContextRepository()
    return create_app(
        unit_of_work_factory=lambda: InMemoryUnitOfWork(
            sessions,
            events,
            contexts,
        ),
        cors_allowed_origins=cors_allowed_origins,
    )


def test_cors_disabled_keeps_health_available_without_cors_header(monkeypatch) -> None:
    async def exercise() -> None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", LOCALHOST_ORIGIN)
        app = create_in_memory_app(())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/health",
                headers={"Origin": LOCALHOST_ORIGIN},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "access-control-allow-origin" not in response.headers

    asyncio.run(exercise())


def test_cors_uses_environment_when_origins_are_not_explicit(monkeypatch) -> None:
    async def exercise() -> None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", LOCALHOST_ORIGIN)
        app = create_in_memory_app(None)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/health",
                headers={"Origin": LOCALHOST_ORIGIN},
            )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == LOCALHOST_ORIGIN

    asyncio.run(exercise())


def test_cors_allows_each_configured_origin_and_not_an_unknown_origin() -> None:
    async def exercise() -> None:
        app = create_in_memory_app((LOCALHOST_ORIGIN, LOOPBACK_ORIGIN))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            for origin in (LOCALHOST_ORIGIN, LOOPBACK_ORIGIN):
                response = await client.get(
                    "/health",
                    headers={"Origin": origin},
                )
                assert response.status_code == 200
                assert response.headers["access-control-allow-origin"] == origin

            unknown_response = await client.get(
                "/health",
                headers={"Origin": "https://example.invalid"},
            )

        assert unknown_response.status_code == 200
        assert unknown_response.json()["status"] == "ok"
        assert "access-control-allow-origin" not in unknown_response.headers

    asyncio.run(exercise())


def test_cors_accepts_post_preflight_with_content_type() -> None:
    async def exercise() -> None:
        app = create_in_memory_app((LOCALHOST_ORIGIN,))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.options(
                "/sessions",
                headers={
                    "Origin": LOCALHOST_ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == LOCALHOST_ORIGIN
        assert "POST" in response.headers["access-control-allow-methods"].split(", ")
        assert "content-type" in {
            header.strip().lower()
            for header in response.headers["access-control-allow-headers"].split(",")
        }

    asyncio.run(exercise())


def test_explicit_origins_override_environment(monkeypatch) -> None:
    async def exercise() -> None:
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS",
            "http://some-env-origin.example",
        )
        app = create_in_memory_app((LOCALHOST_ORIGIN,))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            explicit_response = await client.get(
                "/health",
                headers={"Origin": LOCALHOST_ORIGIN},
            )
            environment_response = await client.get(
                "/health",
                headers={"Origin": "http://some-env-origin.example"},
            )

        assert explicit_response.headers["access-control-allow-origin"] == (
            LOCALHOST_ORIGIN
        )
        assert "access-control-allow-origin" not in environment_response.headers

    asyncio.run(exercise())
