import asyncio

import httpx
from fastapi import FastAPI

from aeroeyes_monitoring_api.domain.identity import uuid7


async def create_session(client: httpx.AsyncClient) -> str:
    response = await client.post("/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


def test_get_existing_context_returns_canonical_response(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session_id = await create_session(client)
            await client.put(
                f"/sessions/{session_id}/context",
                json={
                    "flight_number": " la8084 ",
                    "departure_icao": " sbgr ",
                    "destination_icao": " sbrj ",
                },
            )
            response = await client.get(f"/sessions/{session_id}/context")

        assert response.status_code == 200
        assert response.json() == {
            "session_id": session_id,
            "flight_number": "LA8084",
            "departure_icao": "SBGR",
            "destination_icao": "SBRJ",
        }

    asyncio.run(exercise())


def test_get_distinguishes_missing_session_and_missing_context(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session_id = await create_session(client)
            missing_context = await client.get(
                f"/sessions/{session_id}/context"
            )
            missing_session = await client.get(
                f"/sessions/{uuid7()}/context"
            )

        assert missing_context.status_code == 404
        assert missing_context.json() == {
            "detail": {
                "code": "SESSION_CONTEXT_NOT_FOUND",
                "message": "Session context not found",
            }
        }
        assert missing_session.status_code == 404
        assert missing_session.json() == {
            "detail": {
                "code": "SESSION_NOT_FOUND",
                "message": "Session not found",
            }
        }

    asyncio.run(exercise())


def test_put_creates_then_fully_replaces_context(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session_id = await create_session(client)
            created = await client.put(
                f"/sessions/{session_id}/context",
                json={
                    "flight_number": "LA8084",
                    "departure_icao": "SBGR",
                    "destination_icao": "SBGL",
                },
            )
            replaced = await client.put(
                f"/sessions/{session_id}/context",
                json={"departure_icao": "SBSP"},
            )

        assert created.status_code == 200
        assert replaced.status_code == 200
        assert replaced.json() == {
            "session_id": session_id,
            "flight_number": None,
            "departure_icao": "SBSP",
            "destination_icao": None,
        }

    asyncio.run(exercise())


def test_put_empty_body_creates_and_replaces_with_all_null_context(
    app: FastAPI,
) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first_session_id = await create_session(client)
            created = await client.put(
                f"/sessions/{first_session_id}/context",
                json={},
            )

            second_session_id = await create_session(client)
            await client.put(
                f"/sessions/{second_session_id}/context",
                json={"flight_number": "LA8084"},
            )
            replaced = await client.put(
                f"/sessions/{second_session_id}/context",
                json={},
            )

        assert created.status_code == 200
        assert created.json() == {
            "session_id": first_session_id,
            "flight_number": None,
            "departure_icao": None,
            "destination_icao": None,
        }
        assert replaced.status_code == 200
        assert replaced.json() == {
            "session_id": second_session_id,
            "flight_number": None,
            "departure_icao": None,
            "destination_icao": None,
        }

    asyncio.run(exercise())


def test_put_returns_domain_normalized_values(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session_id = await create_session(client)
            response = await client.put(
                f"/sessions/{session_id}/context",
                json={
                    "flight_number": "  azuL 1234 ",
                    "departure_icao": " sbgr ",
                    "destination_icao": " sbrj ",
                },
            )

        assert response.status_code == 200
        assert response.json()["flight_number"] == "AZUL 1234"
        assert response.json()["departure_icao"] == "SBGR"
        assert response.json()["destination_icao"] == "SBRJ"

    asyncio.run(exercise())


def test_put_rejects_invalid_icao_and_unknown_field(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session_id = await create_session(client)
            invalid_icao = await client.put(
                f"/sessions/{session_id}/context",
                json={"departure_icao": "GRU"},
            )
            unknown_field = await client.put(
                f"/sessions/{session_id}/context",
                json={"aircraft": "PR-ABC"},
            )

        assert invalid_icao.status_code == 422
        assert invalid_icao.json() == {
            "detail": {
                "code": "INVALID_SESSION_CONTEXT",
                "message": (
                    "departure_icao must be exactly 4 ASCII alphabetic characters"
                ),
            }
        }
        assert unknown_field.status_code == 422

    asyncio.run(exercise())


def test_put_missing_parent_returns_structured_404(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/sessions/{uuid7()}/context",
                json={"flight_number": "LA8084"},
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": {
                "code": "SESSION_NOT_FOUND",
                "message": "Session not found",
            }
        }

    asyncio.run(exercise())


def test_delete_is_idempotent_for_existing_parent(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session_with_context = await create_session(client)
            await client.put(
                f"/sessions/{session_with_context}/context",
                json={"flight_number": "LA8084"},
            )
            deleted = await client.delete(
                f"/sessions/{session_with_context}/context"
            )
            deleted_again = await client.delete(
                f"/sessions/{session_with_context}/context"
            )

            session_without_context = await create_session(client)
            absent = await client.delete(
                f"/sessions/{session_without_context}/context"
            )

        for response in (deleted, deleted_again, absent):
            assert response.status_code == 204
            assert response.content == b""

    asyncio.run(exercise())


def test_delete_missing_parent_returns_structured_404(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.delete(
                f"/sessions/{uuid7()}/context"
            )

        assert response.status_code == 404
        assert response.json() == {
            "detail": {
                "code": "SESSION_NOT_FOUND",
                "message": "Session not found",
            }
        }

    asyncio.run(exercise())


def test_malformed_uuid_path_uses_fastapi_validation(app: FastAPI) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            get_response = await client.get("/sessions/not-a-uuid/context")
            put_response = await client.put(
                "/sessions/not-a-uuid/context",
                json={},
            )
            delete_response = await client.delete(
                "/sessions/not-a-uuid/context"
            )

        assert get_response.status_code == 422
        assert put_response.status_code == 422
        assert delete_response.status_code == 422

    asyncio.run(exercise())


def test_openapi_documents_context_routes_and_models(app: FastAPI) -> None:
    schema = app.openapi()
    path = schema["paths"]["/sessions/{session_id}/context"]

    assert set(path) == {"get", "put", "delete"}
    assert path["put"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SessionContextReplaceRequest"
    }
    for operation in (path["get"], path["put"]):
        assert operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/SessionContextResponse"}

    components = schema["components"]["schemas"]
    assert "SessionContextReplaceRequest" in components
    assert "SessionContextResponse" in components
