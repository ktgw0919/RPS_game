"""Boss battle rule judgment (ARCHITECTURE.md §8).

Pure, side-effect-free domain logic for the BOSS (representative) rule. The boss
is a non-competitor who plays every round; participants who beat the boss survive
and earn score. Ties and losses eliminate participants. The boss is never included
in winner/elimination/score participant sets (§8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.models import Hand

# RPS cycle (same as game/engine.py).
_BEATS: dict[Hand, Hand] = {
    Hand.ROCK: Hand.SCISSORS,
    Hand.SCISSORS: Hand.PAPER,
    Hand.PAPER: Hand.ROCK,
}


@dataclass(frozen=True)
class BossRoundOutcome:
    """Result of judging a single BOSS round (ARCHITECTURE.md §8).

    - draw: nobody is eliminated; the same participants replay (§7/§8).
      ``winner_ids`` / ``eliminated_ids`` are empty and ``score_deltas`` is empty.
    - decisive: participants who beat the boss survive (``winner_ids``) with
      +1 score each; others are eliminated. The boss is never listed in either
      tuple.
    """

    is_draw: bool
    winner_ids: tuple[str, ...] = ()
    eliminated_ids: tuple[str, ...] = ()
    score_deltas: tuple[tuple[str, int], ...] = ()


def participant_ids(alive_player_ids: Sequence[str], boss_player_id: str) -> tuple[str, ...]:
    """Alive competitors excluding the boss (§8). Order follows ``alive_player_ids``."""
    return tuple(pid for pid in alive_player_ids if pid != boss_player_id)


def boss_start_ok(eligible_player_ids: Sequence[str], boss_player_id: str | None) -> bool:
    """True when BOSS can start: boss is in S and at least one other participant (§4.2/§8)."""
    if not boss_player_id:
        return False
    if boss_player_id not in eligible_player_ids:
        return False
    return len(eligible_player_ids) >= min_players_for_boss()


def min_players_for_boss() -> int:
    """Minimum |S| for BOSS: boss plus at least one participant (ARCHITECTURE.md §4.2)."""
    return 2


def _beats(attacker: Hand, defender: Hand) -> bool:
    return _BEATS[attacker] is defender


def judge_boss_round(
    alive_player_ids: Sequence[str],
    boss_player_id: str,
    boss_hand: Hand,
    submissions: Mapping[str, Hand],
) -> BossRoundOutcome:
    """Judge one BOSS round (ARCHITECTURE.md §8).

    Each alive participant is compared to ``boss_hand`` individually:
    beat -> survive (+1 score); tie or lose -> eliminated. Non-submitters are
    eliminated on a decisive round (§7). The boss id is ignored in outcomes.
    Safety nets (§7): no participant submissions or zero survivors -> draw.

    Output id order follows ``alive_player_ids`` (participants only).
    """
    participants = participant_ids(alive_player_ids, boss_player_id)
    participant_set = set(participants)
    subs = {pid: hand for pid, hand in submissions.items() if pid in participant_set}

    # §7 safety: no participant submissions -> invalidate (draw, replay).
    if not subs:
        return BossRoundOutcome(is_draw=True)

    winners: list[str] = []
    eliminated: list[str] = []
    score_pairs: list[tuple[str, int]] = []

    for pid in participants:
        hand = subs.get(pid)
        if hand is None:
            eliminated.append(pid)
            continue
        if hand == boss_hand:
            eliminated.append(pid)
        elif _beats(hand, boss_hand):
            winners.append(pid)
            score_pairs.append((pid, 1))
        else:
            eliminated.append(pid)

    # §7 safety: never leave zero survivors -> invalidate (draw, replay).
    if not winners:
        return BossRoundOutcome(is_draw=True)

    return BossRoundOutcome(
        is_draw=False,
        winner_ids=tuple(winners),
        eliminated_ids=tuple(eliminated),
        score_deltas=tuple(score_pairs),
    )
