from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi_cache import FastAPICache
from fastapi_cache.coder import JsonCoder
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.manager import current_optional_user, current_user
from src.auth.models import User
from src.database import get_db

from . import crud, schemas
from .exceptions import LinkExpiredError, NotUniqueAliasError

router = APIRouter(prefix="/links", tags=["links"])

CACHE_TTL_SECONDS = 60


def _cache_key(short_id: str) -> str:
    return f"{FastAPICache.get_prefix()}:redirect:{short_id}"


async def _cache_get_url(short_id: str) -> str | None:
    """Достаём оригинальный URL из кэша. None — кэш холодный или промах."""
    backend = FastAPICache.get_backend()
    try:
        ttl, raw = await backend.get_with_ttl(_cache_key(short_id))
    except Exception:
        return None
    if raw is None or ttl <= 0:
        return None
    return JsonCoder.decode(raw)


async def _cache_put_url(short_id: str, original_url: str) -> None:
    backend = FastAPICache.get_backend()
    try:
        await backend.set(
            _cache_key(short_id),
            JsonCoder.encode(original_url),
            CACHE_TTL_SECONDS,
        )
    except Exception:
        pass


async def _invalidate_redirect_cache(short_id: str) -> None:
    """Удаляем ключ редиректа из кэша. Разные backend'ы ведут себя
    по-разному (InMemory бросает KeyError если ключа нет, Redis — нет);
    абсорбируем разницу.
    """
    backend = FastAPICache.get_backend()
    try:
        await backend.clear(key=_cache_key(short_id))
    except KeyError:
        pass


# 1. Создание ссылки (доступно всем)
@router.post("/shorten", response_model=schemas.LinkResponse)
async def create_short_link(
    link_data: schemas.LinkCreate,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_optional_user),
):
    try:
        return await crud.create_link(
            db=db,
            original_url=str(link_data.original_url),
            custom_alias=link_data.custom_alias,
            expire_at=link_data.expire_at,
            user_id=user.id if user else None,
        )
    except NotUniqueAliasError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=e.detail)


# 2. Редирект (доступно всем). Сам объект `RedirectResponse` плохо переживает
# сериализацию через `@cache`, поэтому кэшируем вручную сам URL — это и
# самое главное для производительности (без кэша каждый GET идёт в Postgres).
@router.get("/{short_id}")
async def redirect_link(
    short_id: str,
    db: AsyncSession = Depends(get_db),
):
    cached_url = await _cache_get_url(short_id)
    if cached_url is not None:
        return RedirectResponse(url=cached_url)

    link = await crud.get_link_by_short_id(db, short_id)
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found")

    if link.expire_at is not None:
        # SQLite не сохраняет tzinfo — нормализуем оба значения к UTC.
        expire_at = link.expire_at
        if expire_at.tzinfo is None:
            expire_at = expire_at.replace(tzinfo=timezone.utc)
        if expire_at < datetime.now(timezone.utc):
            raise LinkExpiredError(short_code=short_id)

    await crud.increment_click_count(db, link)
    await _cache_put_url(short_id, link.original_url)
    return RedirectResponse(url=link.original_url)


# 3. Статистика (только для авторизованных)
@router.get("/{short_id}/stats", response_model=schemas.LinkStatsResponse)
async def get_link_stats(
    short_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    link = await crud.get_link_by_short_id(db, short_id)
    if not link or link.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found")

    return {
        "original_url": link.original_url,
        "short_id": link.short_id,
        "custom_alias": link.custom_alias,
        "created_at": link.created_at,
        "expire_at": link.expire_at,
        "click_count": link.click_count,
    }


# 4. Поиск (только для авторизованных)
@router.get("/search/", response_model=list[schemas.LinkResponse])
async def search_links(
    original_url: str = Query(..., min_length=3),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    return await crud.search_links(db, original_url, user.id)


# 5. Удаление (только для авторизованных)
@router.delete("/{short_id}")
async def delete_link(
    short_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    link = await crud.get_link_by_short_id(db, short_id)
    if not link or link.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found")

    await crud.delete_link(db, link)
    await _invalidate_redirect_cache(short_id)
    return {"status": "success"}


# 6. Обновление (только для авторизованных)
@router.put("/{short_id}", response_model=schemas.LinkResponse)
async def update_link(
    short_id: str,
    update_data: schemas.LinkUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    link = await crud.get_link_by_short_id(db, short_id)
    if not link or link.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found")

    updated = await crud.update_link(db, link, str(update_data.original_url))
    await _invalidate_redirect_cache(short_id)
    return updated
