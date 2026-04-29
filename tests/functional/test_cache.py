"""Тесты кэширования редиректа (`fastapi-cache2` поверх Redis в проде,
in-memory backend в тестах — см. `src/main.py:lifespan`).

Сначала проверяем, что повторные GET после первого «прогрева» **не идут**
в `crud.get_link_by_short_id` — значит ответ отдаётся из кэша. Затем
проверяем инвалидацию на DELETE и PUT.
"""
from datetime import datetime, timedelta, timezone

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

import pytest
import pytest_asyncio

from src.links import crud as crud_module


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="minutes")


@pytest_asyncio.fixture(autouse=True)
async def init_inmemory_cache():
    """В тестах поднимаем кэш в памяти, чтобы декоратор `@cache` работал
    без Redis. После каждого теста очищаем backend.
    """
    FastAPICache.init(InMemoryBackend(), prefix="shortist-cache")
    yield
    backend = FastAPICache.get_backend()
    if hasattr(backend, "clear"):
        await backend.clear()


async def test_redirect_uses_cache_on_repeated_get(
    async_client: AsyncClient, mocker
):
    create = await async_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/cached", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    # Первый GET — прогрев кэша, идёт в БД.
    spy = mocker.spy(crud_module, "get_link_by_short_id")
    first = await async_client.get(f"/links/{short_id}")
    assert first.status_code in (302, 307)
    first_calls = spy.call_count
    assert first_calls >= 1, "первый GET должен сходить в БД"

    # Повторные GET'ы — должны попадать в кэш и не звать crud.get_link_by_short_id.
    for _ in range(5):
        resp = await async_client.get(f"/links/{short_id}")
        assert resp.status_code in (302, 307)

    assert spy.call_count == first_calls, (
        f"повторные GET'ы не должны идти в БД (calls: {spy.call_count}, "
        f"ожидалось: {first_calls})"
    )


async def test_delete_invalidates_redirect_cache(
    authenticated_client: AsyncClient,
):
    """После DELETE редирект должен начать возвращать 404 сразу."""
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    # Прогреваем кэш редиректа.
    pre = await authenticated_client.get(f"/links/{short_id}")
    assert pre.status_code in (302, 307)

    # Удаляем.
    await authenticated_client.delete(f"/links/{short_id}")

    # Если бы кэш не инвалидировался, получили бы старый 302/307.
    after = await authenticated_client.get(f"/links/{short_id}")
    assert after.status_code == 404


async def test_update_invalidates_redirect_cache(
    authenticated_client: AsyncClient,
):
    """После PUT редирект должен пойти на новый URL."""
    create = await authenticated_client.post(
        "/links/shorten",
        json={"original_url": "https://old.example/", "expire_at": _future_iso()},
    )
    short_id = create.json()["short_id"]

    pre = await authenticated_client.get(f"/links/{short_id}")
    assert pre.status_code in (302, 307)
    assert pre.headers["location"].startswith("https://old.example")

    await authenticated_client.put(
        f"/links/{short_id}", json={"original_url": "https://new.example/"}
    )

    after = await authenticated_client.get(f"/links/{short_id}")
    assert after.status_code in (302, 307)
    assert after.headers["location"].startswith("https://new.example"), (
        f"ожидался редирект на новый URL, got {after.headers['location']} "
        "(возможно, кэш не инвалидировался)"
    )
