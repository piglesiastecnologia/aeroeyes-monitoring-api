import asyncio

import httpx

from aeroeyes_monitoring_api.main import app


async def request_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get("/health")


def test_health() -> None:
    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "ok",
        "service": "aeroeyes-monitoring-api",
    }
