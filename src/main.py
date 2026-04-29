import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis

from src.auth.auth import auth_backend
from src.auth.manager import fastapi_users
from src.auth.models import User  # noqa: F401
from src.auth.schemas import UserCreate, UserRead
from src.links.models import Link  # noqa: F401
from src.links.routers import router as links_router

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHE_PREFIX = "shortist-cache"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Подключаем Redis к fastapi-cache2 на старте, отпускаем на стопе.

    В тестах Redis недоступен — на исключении подключения переходим в
    in-memory backend, чтобы не валить функциональные тесты.
    """
    try:
        redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=False)
        await redis.ping()
        FastAPICache.init(RedisBackend(redis), prefix=CACHE_PREFIX)
    except Exception:
        from fastapi_cache.backends.inmemory import InMemoryBackend
        FastAPICache.init(InMemoryBackend(), prefix=CACHE_PREFIX)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    """Лёгкий пинг для healthcheck в docker-compose."""
    return {"status": "ok"}


app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(links_router)
