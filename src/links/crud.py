from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from . import models
from datetime import datetime, timezone
import secrets
import string
from typing import Optional
from .exceptions import NotUniqueAliasError


async def create_link(
        db: AsyncSession,
        original_url: str,
        custom_alias: Optional[str] = None,
        expire_at: Optional[datetime] = None,
        user_id: Optional[int] = None
) -> models.Link:
    if custom_alias:
        existing = await db.execute(
            select(models.Link).filter(models.Link.custom_alias == custom_alias)
        )
        if existing.scalars().first():
            raise NotUniqueAliasError(custom_alias)

    short_id = custom_alias or generate_short_id()
    link = models.Link(
        original_url=original_url,
        short_id=short_id,
        custom_alias=custom_alias,
        user_id=user_id,
        expire_at=expire_at,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def get_link_by_short_id(db: AsyncSession, short_id: str) -> Optional[models.Link]:
    result = await db.execute(
        select(models.Link).filter(models.Link.short_id == short_id)
    )
    return result.scalars().first()


async def increment_click_count(db: AsyncSession, link: models.Link) -> None:
    link.click_count += 1
    await db.commit()


async def search_links(
        db: AsyncSession,
        original_url: str,
        user_id: int
) -> list[models.Link]:
    result = await db.execute(
        select(models.Link)
        .filter(models.Link.original_url.contains(original_url))
        .filter(models.Link.user_id == user_id)
    )
    return result.scalars().all()


async def update_link(
        db: AsyncSession,
        link: models.Link,
        new_url: str
) -> models.Link:
    link.original_url = new_url
    await db.commit()
    await db.refresh(link)
    return link


async def delete_link(db: AsyncSession, link: models.Link) -> None:
    await db.delete(link)
    await db.commit()


def generate_short_id(length=6) -> str:
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))