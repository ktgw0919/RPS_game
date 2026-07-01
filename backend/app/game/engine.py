"""Rock-paper-scissors judgment engine (ARCHITECTURE.md §8, NORMAL rule).

Pure, side-effect-free domain logic: it never touches the store, connections, or
the clock. Given the round's alive set and the submitted hands it returns who
survives and who is eliminated, applying the §8 NORMAL rule and the §7 safety
nets. Match-level concerns (end mode, draw cap, FSM, broadcasts) live in the
orchestration layer (`core/round_runner.py`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.models import Hand

# Each hand beats exactly one other (RPS cycle).
_BEATS: dict[Hand, Hand] = {
    Hand.ROCK: Hand.SCISSORS,
    Hand.SCISSORS: Hand.PAPER,
    Hand.PAPER: Hand.ROCK,
}


@dataclass(frozen=True)
class RoundOutcome:
    """Result of judging a single NORMAL round.

    - draw: nobody is eliminated; the same members replay (§7/§8). Both id tuples
      are empty.
    - decisive: `winner_ids` survive (the winning-hand submitters) and
      `eliminated_ids` lose (the losing-hand submitters plus any alive
      non-submitters, §7 "no submission = loss").
    """

    is_draw: bool
    winner_ids: tuple[str, ...] = ()
    eliminated_ids: tuple[str, ...] = ()


def _winning_hand(hand_a: Hand, hand_b: Hand) -> Hand:
    return hand_a if _BEATS[hand_a] is hand_b else hand_b


def judge_normal_round(
    alive_player_ids: Sequence[str], submissions: Mapping[str, Hand]
) -> RoundOutcome:
    """Judge one NORMAL round (ARCHITECTURE.md §8).

    The §8 rule keys off the distinct *submitted* hands: 1 kind (all same) or 3
    kinds is a draw; exactly 2 kinds is decisive. Alive players who did not submit
    count as losers in a decisive round (§7). Safety nets (§7): if nobody
    submitted, or a decision would leave no survivors, the round is invalidated
    and treated as a draw (replay with the same members).

    Output id order follows `alive_player_ids` for determinism.
    """
    alive = list(alive_player_ids)
    alive_set = set(alive)
    subs = {pid: hand for pid, hand in submissions.items() if pid in alive_set}

    # §7 safety: no submissions at all -> invalidate (draw, replay).
    if not subs:
        return RoundOutcome(is_draw=True)

    distinct = set(subs.values())
    # §8: 1 kind (everyone the same) or all 3 kinds -> draw.
    if len(distinct) != 2:
        return RoundOutcome(is_draw=True)

    hand_a, hand_b = tuple(distinct)
    winning = _winning_hand(hand_a, hand_b)
    winners = tuple(pid for pid in alive if subs.get(pid) is winning)
    winner_set = set(winners)
    eliminated = tuple(pid for pid in alive if pid not in winner_set)

    # §7 safety: never leave zero survivors -> invalidate (draw, replay).
    if not winners:
        return RoundOutcome(is_draw=True)

    return RoundOutcome(is_draw=False, winner_ids=winners, eliminated_ids=eliminated)
