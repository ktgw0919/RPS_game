"""Lightweight in-memory rate limiting (ARCHITECTURE.md §3.1/§11).

Used to throttle room creation per client IP. This is a simple sliding-window
counter suitable for the single-worker MVP; a token-bucket / shared store can
replace it later when scaling out.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, max_events: int, window_sec: int) -> None:
        self._max = max_events
        self._window = window_sec
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record an attempt for `key`; return False if it exceeds the limit."""
        ts = time.monotonic() if now is None else now
        bucket = self._hits[key]
        cutoff = ts - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self._max:
            return False
        bucket.append(ts)
        return True
