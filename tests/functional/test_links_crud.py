"""Функциональные тесты CRUD-операций над ссылками: create / stats / update / delete / search."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="minutes")


async def test_anonymous_can_create_link(async_client: AsyncClient):
    resp = await async_client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com",
            "expire_at": _future_iso(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["original_url"].startswith("https://example.com")
    assert isinstance(body["short_id"], str)
    assert len(body["short_id"]) == 6
    assert body["custom_alias"] is None


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Баг 4: crud.create_link не сохраняет custom_alias в модель — "
        "поле сохраняется только как short_id, а custom_alias остаётся NULL. "
        "Поэтому в ответе custom_alias=null, тест краснеет до фикса в PR #2."
    ),
)
async def test_create_link_with_custom_alias(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com",
            "custom_alias": "my-link",
            "expire_at": _future_iso(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["custom_alias"] == "my-link"
    assert body["short_id"] == "my-link"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Связано с багом 4: проверка уникальности alias в crud.create_link "
        "идёт по полю custom_alias, которое всегда NULL. "
        "Из-за этого второй POST не ловится в коде, валится UNIQUE constraint "
        "на short_id и FastAPI возвращает 500 вместо 400. Фикс в PR #2."
    ),
)
async def test_duplicate_alias_returns_400(authenticated_client: AsyncClient):
    payload = {
        "original_url": "https://example.com",
        "custom_alias": "twice",
        "expire_at": _future_iso(),
    }
    first = await authenticated_client.post("/links/shorten", json=payload)
    assert first.status_code == 200
    second = await authenticated_client.post("/links/shorten", json=payload)
    assert second.status_code == 400
    assert "already exists" in second.json()["detail"]


async def test_invalid_url_returns_422(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "not-a-url", "expire_at": _future_iso()},
    )
    assert resp.status_code == 422


async def test_invalid_alias_chars_return_422(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com",
            "custom_alias": "bad alias!",
            "expire_at": _future_iso(),
        },
    )
    assert resp.status_code == 422


async def test_get_stats_for_own_link(authenticated_client: AsyncClient):
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    stats = await authenticated_client.get(f"/links/{short_id}/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert body["short_id"] == short_id
    assert body["click_count"] == 0


async def test_stats_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/links/abc123/stats")
    assert resp.status_code == 401


async def test_update_own_link(authenticated_client: AsyncClient):
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    upd = await authenticated_client.put(
        f"/links/{short_id}",
        json={"original_url": "https://updated.example.com"},
    )
    assert upd.status_code == 200
    assert upd.json()["original_url"].startswith("https://updated.example.com")


async def test_delete_own_link(authenticated_client: AsyncClient):
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    delete = await authenticated_client.delete(f"/links/{short_id}")
    assert delete.status_code == 200
    assert delete.json()["status"] == "success"

    # после удаления статистика должна вернуть 404
    stats = await authenticated_client.get(f"/links/{short_id}/stats")
    assert stats.status_code == 404


async def test_search_finds_user_links(authenticated_client: AsyncClient):
    await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/page-a", "expire_at": _future_iso()},
    )
    await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/page-b", "expire_at": _future_iso()},
    )
    await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://other.example/page", "expire_at": _future_iso()},
    )

    resp = await authenticated_client.get("/links/search/?original_url=example.com")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    for item in body:
        assert "example.com" in item["original_url"]


async def test_search_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/links/search/?original_url=foo")
    assert resp.status_code == 401


async def test_search_min_query_length(authenticated_client: AsyncClient):
    resp = await authenticated_client.get("/links/search/?original_url=ab")  # < 3
    assert resp.status_code == 422
