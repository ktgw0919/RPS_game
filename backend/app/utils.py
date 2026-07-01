"""Generic helpers only (ARCHITECTURE.md §2).

Time formatting and room-code generation. No domain/infrastructure logic here
(those belong in `core/` and `game/`).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from app.core.constants import ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH


def utcnow() -> datetime:
    """Timezone-aware current time in UTC."""
    return datetime.now(UTC)


def isoformat_utc(dt: datetime) -> str:
    """Format a datetime as UTC ISO8601 with millisecond precision and 'Z'.

    Example: 2026-06-29T08:00:00.000Z (ARCHITECTURE.md §4 time convention).
    Naive datetimes are assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    # Millisecond precision, drop the +00:00 offset and append 'Z'.
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def generate_room_code() -> str:
    """Generate a single random room code (collision handling is the caller's job)."""
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


def generate_match_id() -> str:
    """Generate an opaque match id (not a secret; just unique within a process)."""
    return secrets.token_urlsafe(12)
