from httpx import AsyncClient


async def test_health_endpoint_returns_200(async_client: AsyncClient):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
