import asyncio

import httpx
from fastapi import FastAPI


async def request_health(app: FastAPI) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get("/health")


def test_health(app: FastAPI) -> None:
    response = asyncio.run(request_health(app))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "ok",
        "service": "aeroeyes-monitoring-api",
    }
