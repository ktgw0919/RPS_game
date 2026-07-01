"""Tests for the sliding-window rate limiter (ARCHITECTURE.md §3.1)."""

from __future__ import annotations

from app.core.rate_limit import SlidingWindowRateLimiter


def test_allows_up_to_max() -> None:
    limiter = SlidingWindowRateLimiter(max_events=3, window_sec=600)
    assert [limiter.allow("ip", now=t) for t in (0, 1, 2)] == [True, True, True]
    assert limiter.allow("ip", now=3) is False


def test_window_slides() -> None:
    limiter = SlidingWindowRateLimiter(max_events=2, window_sec=10)
    assert limiter.allow("ip", now=0) is True
    assert limiter.allow("ip", now=1) is True
    assert limiter.allow("ip", now=2) is False
    # After the window passes, earlier hits expire.
    assert limiter.allow("ip", now=12) is True


def test_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter(max_events=1, window_sec=600)
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("b", now=0) is True
    assert limiter.allow("a", now=1) is False
