"""CPU helper unit tests (ARCHITECTURE.md §6)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.constants import CPU_SUBMIT_DELAY_EPSILON_SEC
from app.game.cpu import (
    compute_submit_delay,
    last_cpu_player_id,
    next_cpu_display_name,
    pick_random_hand,
)
from app.models import CpuStrategy, Hand, Player

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _cpu(player_id: str, *, joined: datetime = NOW) -> Player:
    return Player(
        player_id=player_id,
        token=None,
        display_name=player_id,
        is_cpu=True,
        cpu_strategy=CpuStrategy.RANDOM,
        joined_at=joined,
    )


def test_next_cpu_display_name_increments() -> None:
    members = {"a": _cpu("CPU-1")}
    assert next_cpu_display_name(members) == "CPU-2"


def test_last_cpu_player_id_picks_newest() -> None:
    early = NOW
    late = datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)
    members = {
        "a": _cpu("a", joined=early),
        "b": _cpu("b", joined=late),
    }
    assert last_cpu_player_id(members) == "b"


def test_pick_random_hand_is_deterministic_with_injected_uniform() -> None:
    assert pick_random_hand(uniform=lambda _a, _b: 0.0) == Hand.ROCK
    assert pick_random_hand(uniform=lambda _a, _b: 2.5) == Hand.PAPER


def test_compute_submit_delay_clamps_before_deadline() -> None:
    short_limit = CPU_SUBMIT_DELAY_EPSILON_SEC + 0.1
    delay = compute_submit_delay(short_limit, uniform=lambda _a, _b: 99.0)
    assert delay == short_limit - CPU_SUBMIT_DELAY_EPSILON_SEC
