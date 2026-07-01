"""CPU player helpers (ARCHITECTURE.md §3/§6).

CPU players have no token or WebSocket connection; the server generates hands
and registers submissions on their behalf after a short, clamped random delay.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping

from app.core.constants import (
    CPU_SUBMIT_DELAY_EPSILON_SEC,
    CPU_SUBMIT_DELAY_MAX_SEC,
    CPU_SUBMIT_DELAY_MIN_SEC,
)
from app.models import CpuStrategy, Hand, Player

type UniformFn = Callable[[float, float], float]


def next_cpu_display_name(members: Mapping[str, Player]) -> str:
    """Allocate the next `CPU-N` display name for a room (§6)."""
    nums: list[int] = []
    for player in members.values():
        if not player.is_cpu:
            continue
        name = player.display_name
        if name.startswith("CPU-"):
            try:
                nums.append(int(name[4:]))
            except ValueError:
                continue
    return f"CPU-{max(nums, default=0) + 1}"


def last_cpu_player_id(members: Mapping[str, Player]) -> str | None:
    """Return the most recently joined CPU member id, or None."""
    cpus = [p for p in members.values() if p.is_cpu]
    if not cpus:
        return None
    return max(cpus, key=lambda p: p.joined_at).player_id


def pick_random_hand(
    *,
    strategy: CpuStrategy = CpuStrategy.RANDOM,
    uniform: UniformFn = random.uniform,
) -> Hand:
    """Pick a hand for a CPU player (MVP: RANDOM only)."""
    if strategy is not CpuStrategy.RANDOM:
        raise ValueError(f"Unsupported CPU strategy: {strategy}")
    idx = int(uniform(0, 3))
    return (Hand.ROCK, Hand.SCISSORS, Hand.PAPER)[idx % 3]


def compute_submit_delay(
    round_time_limit_sec: float,
    *,
    uniform: UniformFn = random.uniform,
) -> float:
    """Clamp CPU auto-submit delay so it always lands before the deadline (§6)."""
    raw = uniform(CPU_SUBMIT_DELAY_MIN_SEC, CPU_SUBMIT_DELAY_MAX_SEC)
    cap = max(0.0, round_time_limit_sec - CPU_SUBMIT_DELAY_EPSILON_SEC)
    return min(raw, cap)
