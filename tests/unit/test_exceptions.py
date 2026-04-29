"""Юнит-тесты доменных исключений `src/links/exceptions.py`.

Эти исключения образуют публичный «контракт» — каждое объявляет конкретный
HTTP-код и формат detail. Тесты фиксируют контракт независимо от того,
вызывается ли каждое исключение в текущем коде (часть из них в момент PR #1
не используется — это отдельная находка, см. README).
"""
from fastapi import status

from src.links.exceptions import (
    AliasLengthError,
    InvalidURLFormatError,
    LinkException,
    LinkExpiredError,
    NotUniqueAliasError,
    PermissionDeniedError,
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


def test_alias_length_error_default_bounds():
    err = AliasLengthError(alias="ab")
    assert err.status_code == status.HTTP_400_BAD_REQUEST
    assert "ab" in err.detail
    assert "5" in err.detail and "15" in err.detail


def test_alias_length_error_custom_bounds():
    err = AliasLengthError(alias="x", min_len=4, max_len=16)
    assert "4" in err.detail and "16" in err.detail


def test_link_expired_error():
    err = LinkExpiredError(short_code="abc123")
    assert err.status_code == status.HTTP_410_GONE
    assert "abc123" in err.detail
    assert "expired" in err.detail


def test_permission_denied_default():
    err = PermissionDeniedError()
    assert err.status_code == status.HTTP_403_FORBIDDEN
    assert "perform this action" in err.detail


def test_permission_denied_custom_action():
    err = PermissionDeniedError(action="delete this link")
    assert "delete this link" in err.detail


def test_invalid_url_format_error():
    err = InvalidURLFormatError(url="not-a-url")
    assert err.status_code == status.HTTP_400_BAD_REQUEST
    assert "not-a-url" in err.detail
    assert "http://" in err.detail
