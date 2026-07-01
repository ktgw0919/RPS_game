"""Player token issuance and verification (ARCHITECTURE.md §3).

No authentication is performed; a lightweight, high-entropy player token is the
only proof of identity. Tokens are compared in constant time to avoid timing
leaks. Tokens are returned only in REST response bodies and presented later in
the first WS `JOIN` message (never in URLs/query/logs).
"""

from __future__ import annotations

import secrets

# 32 bytes -> 256 bits of entropy (well above the 128-bit minimum).
_TOKEN_NBYTES = 32


def generate_player_id() -> str:
    """Generate an opaque, URL-safe player id."""
    return secrets.token_urlsafe(12)


def generate_player_token() -> str:
    """Generate a high-entropy, URL-safe player token (>=128 bits)."""
    return secrets.token_urlsafe(_TOKEN_NBYTES)


def verify_token(expected: str | None, provided: str) -> bool:
    """Constant-time token comparison. CPU players (expected=None) never match."""
    if not expected:
        return False
    return secrets.compare_digest(expected, provided)
