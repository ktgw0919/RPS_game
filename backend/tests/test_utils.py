"""Unit tests for generic helpers and value validation."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timezone

import pytest

from app.core.constants import ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH
from app.models import normalize_display_name
from app.utils import generate_room_code, isoformat_utc, normalize_room_code

_ISO_MS_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_isoformat_utc_has_millis_and_z() -> None:
    dt = datetime(2026, 6, 29, 8, 0, 0, 123456, tzinfo=UTC)
    assert isoformat_utc(dt) == "2026-06-29T08:00:00.123Z"


def test_isoformat_utc_matches_convention() -> None:
    assert _ISO_MS_Z.match(isoformat_utc(datetime.now(UTC)))


def test_isoformat_utc_converts_to_utc() -> None:
    from datetime import timedelta

    jst = timezone(timedelta(hours=9))
    dt = datetime(2026, 6, 29, 17, 0, 0, tzinfo=jst)
    assert isoformat_utc(dt) == "2026-06-29T08:00:00.000Z"


def test_generate_room_code_shape() -> None:
    code = generate_room_code()
    assert len(code) == ROOM_CODE_LENGTH
    assert all(ch in ROOM_CODE_ALPHABET for ch in code)
    # Ambiguous characters must be excluded.
    assert not (set(code) & set("0O1IL"))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Alice  ", "Alice"),
        ("Bob\tCarol", "BobCarol"),
        ("🎮Player", "🎮Player"),
        ("日本語", "日本語"),
    ],
)
def test_normalize_display_name_ok(raw: str, expected: str) -> None:
    assert normalize_display_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\n\t", "x" * 21])
def test_normalize_display_name_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_display_name(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abcd", "ABCD"),
        ("  wxyz  ", "WXYZ"),
    ],
)
def test_normalize_room_code_ok(raw: str, expected: str) -> None:
    assert normalize_room_code(raw) == expected


@pytest.mark.parametrize("raw", ["", "ABC", "ABCDE", "AB1D", "ABCD!", "OOOO"])
def test_normalize_room_code_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_room_code(raw)
