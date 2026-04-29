"""Функциональные тесты регистрации/логина/логаута через httpx ASGI-клиент."""
from httpx import AsyncClient


async def test_register_creates_user(async_client: AsyncClient):
    resp = await async_client.post(
        "/auth/register",
        json={"id": 1, "email": "alice@example.com", "password": "Str0ng!Pass"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"


async def test_register_duplicate_email_rejected(async_client: AsyncClient):
    payload = {"id": 1, "email": "dup@example.com", "password": "Str0ng!Pass"}
    first = await async_client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await async_client.post("/auth/register", json=payload)
    assert second.status_code == 400


async def test_login_with_valid_credentials(async_client: AsyncClient):
    email, password = "login@example.com", "Str0ng!Pass"
    await async_client.post(
        "/auth/register", json={"id": 1, "email": email, "password": password}
    )
    resp = await async_client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code in (200, 204)
    # cookie выставляется как `shortist`
    assert any(c.name == "shortist" for c in resp.cookies.jar)


async def test_login_with_wrong_password(async_client: AsyncClient):
    email = "wrong@example.com"
    await async_client.post(
        "/auth/register", json={"id": 1, "email": email, "password": "Str0ng!Pass"}
    )
    resp = await async_client.post(
        "/auth/jwt/login",
        data={"username": email, "password": "totally-wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400


async def test_login_unknown_user(async_client: AsyncClient):
    resp = await async_client.post(
        "/auth/jwt/login",
        data={"username": "nobody@example.com", "password": "anything"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400


async def test_logout_clears_session(authenticated_client: AsyncClient):
    resp = await authenticated_client.post("/auth/jwt/logout")
    assert resp.status_code in (200, 204)
