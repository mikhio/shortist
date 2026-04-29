"""Юнит-тесты Pydantic-валидаторов схем `LinkCreate`/`LinkBase`/`LinkUpdate`."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.links.schemas import LinkCreate, LinkUpdate


def _future(days: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def _past(days: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


class TestLinkCreate:
    def test_https_url_accepted(self):
        link = LinkCreate(original_url="https://example.com", expire_at=_future())
        assert str(link.original_url).startswith("https://")

    def test_http_url_accepted(self):
        link = LinkCreate(original_url="http://example.com", expire_at=_future())
        assert str(link.original_url).startswith("http://")

    def test_expire_in_past_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LinkCreate(original_url="https://example.com", expire_at=_past())
        assert "future" in str(exc.value).lower() or "expire" in str(exc.value).lower()

    def test_expire_seconds_truncated(self):
        future_with_seconds = _future().replace(second=42, microsecond=999)
        link = LinkCreate(original_url="https://example.com", expire_at=future_with_seconds)
        assert link.expire_at.second == 0
        assert link.expire_at.microsecond == 0

    def test_custom_alias_too_short(self):
        with pytest.raises(ValidationError):
            LinkCreate(
                original_url="https://example.com",
                expire_at=_future(),
                custom_alias="ab",  # < 4 символов
            )

    def test_custom_alias_too_long(self):
        with pytest.raises(ValidationError):
            LinkCreate(
                original_url="https://example.com",
                expire_at=_future(),
                custom_alias="a" * 17,  # > 16 символов
            )

    def test_custom_alias_invalid_chars(self):
        with pytest.raises(ValidationError):
            LinkCreate(
                original_url="https://example.com",
                expire_at=_future(),
                custom_alias="bad alias!",
            )

    def test_custom_alias_valid(self):
        link = LinkCreate(
            original_url="https://example.com",
            expire_at=_future(),
            custom_alias="my-link_42",
        )
        assert link.custom_alias == "my-link_42"

    def test_expire_none_passes(self):
        link = LinkCreate(original_url="https://example.com", expire_at=None)
        assert link.expire_at is None


class TestLinkUpdate:
    def test_round_expire_seconds(self):
        future_with_seconds = _future().replace(second=33, microsecond=777)
        upd = LinkUpdate(expire_at=future_with_seconds)
        assert upd.expire_at.second == 0
        assert upd.expire_at.microsecond == 0

    def test_expire_none_returns_none(self):
        upd = LinkUpdate(expire_at=None)
        assert upd.expire_at is None

    def test_url_optional(self):
        upd = LinkUpdate()
        assert upd.original_url is None
        assert upd.expire_at is None
