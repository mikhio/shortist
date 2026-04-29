"""Тесты на проверку срока действия ссылки.

В PR #1 эти тесты обнаруживают баг: `expire_at` сохраняется в БД, но при
редиректе `GET /links/{short_id}` не проверяется. Просроченная ссылка
продолжает редиректить, хотя в `src/links/exceptions.py` уже определён
`LinkExpiredError` с кодом 410.

В PR #2 баг чинится в `src/links/routers.py:redirect_link`, и эти тесты
становятся зелёными.
"""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.links.models import Link


async def _make_expired(session_factory: async_sessionmaker, short_id: str) -> None:
    """Сдвигаем `expire_at` в БД назад во времени, в обход Pydantic-валидатора."""
    async with session_factory() as session:
        result = await session.execute(select(Link).where(Link.short_id == short_id))
        link = result.scalars().first()
        assert link is not None
        link.expire_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()


async def test_expired_link_returns_410(
    async_client: AsyncClient, test_session_factory: async_sessionmaker
):
    create = await async_client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com",
            "expire_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="minutes"),
        },
    )
    assert create.status_code == 200
    short_id = create.json()["short_id"]

    await _make_expired(test_session_factory, short_id)

    resp = await async_client.get(f"/links/{short_id}")
    assert resp.status_code == 410, (
        f"ожидался 410 Gone для просроченной ссылки, получили {resp.status_code} "
        "(баг: expire_at не проверяется в redirect_link)"
    )


async def test_active_link_still_redirects(
    async_client: AsyncClient, test_session_factory: async_sessionmaker
):
    """Контрольный тест: непросроченная ссылка должна редиректить нормально."""
    create = await async_client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com",
            "expire_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec="minutes"),
        },
    )
    short_id = create.json()["short_id"]

    resp = await async_client.get(f"/links/{short_id}")
    assert resp.status_code in (302, 307)
