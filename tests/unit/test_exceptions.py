"""Юнит-тесты доменных исключений `src/links/exceptions.py`.

После PR #2 в файле остались только реально используемые исключения:
`NotUniqueAliasError` и `LinkExpiredError`. Мёртвые `AliasLengthError`,
`PermissionDeniedError`, `InvalidURLFormatError` удалены.
"""
from fastapi import status

from src.links.exceptions import (
    LinkException,
    LinkExpiredError,
    NotUniqueAliasError,
)


def test_link_exception_is_http_exception():
    err = LinkException(status_code=418, detail="teapot")
    assert err.status_code == 418
    assert err.detail == "teapot"


def test_not_unique_alias_error():
    err = NotUniqueAliasError(alias="my-link")
    assert err.status_code == status.HTTP_400_BAD_REQUEST
    assert "my-link" in err.detail
    assert "already exists" in err.detail


def test_link_expired_error():
    err = LinkExpiredError(short_code="abc123")
    assert err.status_code == status.HTTP_410_GONE
    assert "abc123" in err.detail
    assert "expired" in err.detail
