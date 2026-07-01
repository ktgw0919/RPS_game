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
    """Pick a random hand for a CPU player."""
    if strategy is not CpuStrategy.RANDOM:
        raise ValueError(f"Unsupported random CPU strategy: {strategy}")
    idx = int(uniform(0, 3))
    return (Hand.ROCK, Hand.SCISSORS, Hand.PAPER)[idx % 3]


def pick_cpu_hand(
    player: Player,
    *,
    uniform: UniformFn = random.uniform,
) -> Hand:
    """Pick the next hand for a CPU player according to its strategy."""
    strategy = player.cpu_strategy or CpuStrategy.RANDOM
    if strategy is CpuStrategy.FIXED:
        if not player.cpu_fixed_hands:
            raise ValueError(f"CPU {player.player_id} has FIXED strategy but no fixed_hands")
        idx = player.cpu_fixed_hand_index % len(player.cpu_fixed_hands)
        return player.cpu_fixed_hands[idx]
    return pick_random_hand(strategy=strategy, uniform=uniform)


def advance_cpu_hand_index(player: Player) -> None:
    """Advance scripted-hand cursor after a CPU submission (FIXED strategy only)."""
    if player.cpu_strategy is CpuStrategy.FIXED and player.cpu_fixed_hands:
        player.cpu_fixed_hand_index += 1


def compute_submit_delay(
    round_time_limit_sec: float,
    *,
    uniform: UniformFn = random.uniform,
) -> float:
    """Clamp CPU auto-submit delay so it always lands before the deadline (§6)."""
    raw = uniform(CPU_SUBMIT_DELAY_MIN_SEC, CPU_SUBMIT_DELAY_MAX_SEC)
    cap = max(0.0, round_time_limit_sec - CPU_SUBMIT_DELAY_EPSILON_SEC)
    return min(raw, cap)
