"""Общие фикстуры pytest для функциональных тестов shortist.

Поднимаем приложение поверх in-memory SQLite, подменяем зависимость `get_db`
через `app.dependency_overrides`. Каждая тестовая функция получает чистую
схему БД.

Источники:
- FastAPI Testing: https://fastapi.tiangolo.com/advanced/async-tests/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io
"""
import os

# ENV должны быть выставлены ДО импортов src.*, иначе src/database.py упадёт
# на построении DATABASE_URL для Postgres.
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "shortist_test")
os.environ.setdefault("SECRET", "test-secret-not-for-production")

import asyncio
import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Импортируем приложение и метаданные ПОСЛЕ выставления ENV.
from src import database as src_database  # noqa: E402
from src.database import Base, get_db  # noqa: E402
from src.main import app  # noqa: E402

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _init_cache_for_tests():
    """В тестах поднимаем in-memory backend для fastapi-cache2.

    Lifespan приложения через ASGITransport срабатывает ненадёжно (зависит
    от версии httpx/starlette), поэтому инициализируем кэш напрямую — это
    гарантирует, что декоратор `@cache` в `redirect_link` не падает на
    `FastAPICache.get_prefix()`.
    """
    FastAPICache.init(InMemoryBackend(), prefix="shortist-cache")
    yield
    # сбрасываем состояние, чтобы кэш одного теста не утекал в следующий
    FastAPICache.reset()


@pytest.fixture(scope="session")
def event_loop():
    """Один loop на сессию — иначе async-фикстуры рассыпаются между тестами."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_engine():
    """Свежий in-memory engine на каждый тест → полная изоляция."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_factory(test_engine):
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def db_session(test_session_factory) -> AsyncIterator[AsyncSession]:
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(test_session_factory) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент с подменённой `get_db` под тестовый engine."""

    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    # `fastapi_users` использует ту же `get_db` транзитивно, патч покрывает всё.

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


# ---- helpers для аутентификации ----


def _unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


@pytest_asyncio.fixture
async def registered_user(async_client: AsyncClient) -> dict:
    """Регистрирует свежего юзера, возвращает {email, password}."""
    email = _unique_email()
    password = "Str0ngP@ssw0rd!"
    resp = await async_client.post(
        "/auth/register",
        json={
            "id": 1,  # игнорируется бекендом, но требуется UserCreate-схемой
            "email": email,
            "password": password,
        },
    )
    assert resp.status_code == 201, resp.text
    return {"email": email, "password": password, "data": resp.json()}


@pytest_asyncio.fixture
async def authenticated_client(
    async_client: AsyncClient, registered_user: dict
) -> AsyncClient:
    """Клиент с уже выставленной auth-cookie.

    httpx + ASGITransport не переносит cookie автоматически между запросами
    (related: https://github.com/encode/httpx/issues/2992), поэтому явно
    переносим выданный токен в `client.cookies` после логина.
    """
    resp = await async_client.post(
        "/auth/jwt/login",
        data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code in (200, 204), resp.text
    token = resp.cookies.get("shortist")
    assert token, "auth cookie не выдалась"
    async_client.cookies.set("shortist", token)
    return async_client


@pytest_asyncio.fixture
async def another_authenticated_client(
    test_session_factory,
) -> AsyncIterator[AsyncClient]:
    """Второй клиент с собственным юзером — для тестов прав доступа."""

    async def _override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        email = _unique_email("other")
        password = "An0therStr0ng!"
        reg = await client.post(
            "/auth/register",
            json={"id": 2, "email": email, "password": password},
        )
        assert reg.status_code == 201, reg.text

        login = await client.post(
            "/auth/jwt/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login.status_code in (200, 204), login.text
        token = login.cookies.get("shortist")
        assert token
        client.cookies.set("shortist", token)
        yield client

    app.dependency_overrides.clear()
