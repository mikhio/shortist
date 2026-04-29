"""Тест на ручку `/health`.

В PR #1 этот тест краснеет — ручки нет, хотя `docker-compose.yaml` ссылается
на неё в healthcheck контейнера `app`, что ломает поднятие compose.

В PR #2 в `src/main.py` добавляется `@app.get("/health")` и тест зеленеет.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Баг 2: ручка /health не реализована в src/main.py, хотя на неё "
        "ссылается healthcheck в docker-compose.yaml — контейнер app поднимается "
        "как unhealthy. Фикс в PR #2."
    ),
)
async def test_health_endpoint_returns_200(async_client: AsyncClient):
    resp = await async_client.get("/health")
    assert resp.status_code == 200, (
        f"ожидался 200 OK на /health, получили {resp.status_code} "
        "(баг: ручки нет, healthcheck в docker-compose валится)"
    )
    body = resp.json()
    assert body.get("status") == "ok"
