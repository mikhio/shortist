"""Тесты прав доступа: чужие ссылки не должны быть видны/редактируемы."""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="minutes")


async def test_other_user_cannot_get_stats(
    authenticated_client: AsyncClient,
    another_authenticated_client: AsyncClient,
):
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://owner.example", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    # `another_authenticated_client` использует тот же `test_session_factory`,
    # поэтому ссылка видна обоим клиентам в БД. Сервис специально прячет 403
    # как 404 в `routers.py:get_link_stats`, чтобы не подсказывать перебором,
    # какие short_id заняты — поэтому ожидаем именно 404.
    resp = await another_authenticated_client.get(f"/links/{short_id}/stats")
    assert resp.status_code == 404


async def test_unauthenticated_cannot_delete(async_client: AsyncClient):
    resp = await async_client.delete("/links/abc123")
    assert resp.status_code == 401


async def test_unauthenticated_cannot_update(async_client: AsyncClient):
    resp = await async_client.put(
        "/links/abc123",
        json={"original_url": "https://x.example"},
    )
    assert resp.status_code == 401


async def test_owner_delete_then_404(authenticated_client: AsyncClient):
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    await authenticated_client.delete(f"/links/{short_id}")
    # повторное удаление → 404
    second = await authenticated_client.delete(f"/links/{short_id}")
    assert second.status_code == 404


async def test_update_unknown_returns_404(authenticated_client: AsyncClient):
    resp = await authenticated_client.put(
        "/links/no-such-link-xx",
        json={"original_url": "https://x.example"},
    )
    assert resp.status_code == 404
