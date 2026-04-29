"""Тесты ручки редиректа `GET /links/{short_id}`."""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="minutes")


async def test_redirect_to_original_url(async_client: AsyncClient):
    create = await async_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/page", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    # follow_redirects=False по умолчанию у httpx
    resp = await async_client.get(f"/links/{short_id}")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].startswith("https://example.com/page")


async def test_redirect_increments_click_count(authenticated_client: AsyncClient):
    """Первый редирект инкрементирует счётчик. Последующие могут идти из
    кэша и не доходить до БД — это сознательный tradeoff (см. README,
    раздел про кэширование). Поэтому проверяем только что счётчик хотя
    бы один раз вырос.
    """
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    for _ in range(3):
        resp = await authenticated_client.get(f"/links/{short_id}")
        assert resp.status_code in (302, 307)

    stats = await authenticated_client.get(f"/links/{short_id}/stats")
    assert stats.status_code == 200
    assert stats.json()["click_count"] >= 1


async def test_unknown_short_id_returns_404(async_client: AsyncClient):
    resp = await async_client.get("/links/no-such-id-xx")
    assert resp.status_code == 404
