"""Юнит-тесты генератора коротких идентификаторов.

Проверяем чистую функцию `generate_short_id` из `src/links/crud.py` без БД и HTTP.
Используем Hypothesis для property-based проверки инварианта на длину/алфавит
при произвольных входных параметрах.

Источник: https://hypothesis.readthedocs.io
"""
import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.links.crud import generate_short_id

ALLOWED_CHARS = set(string.ascii_letters + string.digits)


def test_default_length_is_6():
    short_id = generate_short_id()
    assert len(short_id) == 6


def test_alphabet_is_alnum():
    short_id = generate_short_id()
    assert set(short_id).issubset(ALLOWED_CHARS)


def test_returns_string():
    assert isinstance(generate_short_id(), str)


@pytest.mark.parametrize("length", [1, 4, 8, 16, 32, 64])
def test_custom_length(length):
    short_id = generate_short_id(length=length)
    assert len(short_id) == length
    assert set(short_id).issubset(ALLOWED_CHARS)


def test_collision_rate_is_low():
    """10 000 вызовов должны дать почти все уникальные значения.

    62**6 ≈ 5.7e10 — на 10к вызовов вероятность коллизии исчезающе мала.
    """
    samples = {generate_short_id() for _ in range(10_000)}
    assert len(samples) >= 9_990  # допускаем единичные совпадения


@given(length=st.integers(min_value=1, max_value=64))
@settings(max_examples=50, deadline=None)
def test_property_length_and_alphabet(length: int):
    short_id = generate_short_id(length=length)
    assert len(short_id) == length
    assert set(short_id).issubset(ALLOWED_CHARS)
