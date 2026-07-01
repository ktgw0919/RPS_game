"""Minority rule judgment (ARCHITECTURE.md §8).

Pure, side-effect-free domain logic: it never touches the store, connections, or
the clock. Given the round's alive set and the submitted hands it returns who
survives and who is eliminated under the MINORITY rule, and helpers for the
threshold-based transition to NORMAL finish (§8/§9).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.game.engine import RoundOutcome
from app.models import Hand, MinorityFinishTiming, RuleType


def judge_minority_round(
    alive_player_ids: Sequence[str], submissions: Mapping[str, Hand]
) -> RoundOutcome:
    """Judge one MINORITY round (ARCHITECTURE.md §8).

    Count submitters per hand; players who submitted the unique minimum-count
    hand survive. All same hand / tied minimum counts -> draw (§8).
    Alive non-submitters lose on a decisive round (§7). Safety nets (§7):
    no submissions or zero survivors -> draw.

    Output id order follows `alive_player_ids` for determinism.
    """
    alive = list(alive_player_ids)
    alive_set = set(alive)
    subs = {pid: hand for pid, hand in submissions.items() if pid in alive_set}

    # §7 safety: no submissions at all -> invalidate (draw, replay).
    if not subs:
        return RoundOutcome(is_draw=True)

    counts = Counter(subs.values())
    distinct = set(counts.keys())

    # §8: all same hand -> draw.
    if len(distinct) == 1:
        return RoundOutcome(is_draw=True)

    min_count = min(counts.values())
    min_hands = [hand for hand, cnt in counts.items() if cnt == min_count]

    # §8: multiple hands tie for minimum -> draw.
    if len(min_hands) != 1:
        return RoundOutcome(is_draw=True)

    minority_hand = min_hands[0]
    winners = tuple(pid for pid in alive if subs.get(pid) == minority_hand)
    winner_set = set(winners)
    eliminated = tuple(pid for pid in alive if pid not in winner_set)

    # §7 safety: never leave zero survivors -> invalidate (draw, replay).
    if not winners:
        return RoundOutcome(is_draw=True)

    return RoundOutcome(is_draw=False, winner_ids=winners, eliminated_ids=eliminated)


@dataclass(frozen=True)
class NormalFinishTransition:
    """Whether the match should switch from MINORITY to NORMAL finish (§8/§9).

    - ``switch_now``: apply NORMAL judging for the remainder of this match
      (``minority_finish_timing=IMMEDIATE`` and survivors at or below threshold).
    - ``defer_to_next_match``: threshold met but ``NEXT_MATCH`` timing — keep
      minority rules for this match; the next ``START_GAME`` should use NORMAL.
    """

    switch_now: bool
    defer_to_next_match: bool


def evaluate_normal_finish_transition(
    survivor_count: int,
    threshold: int,
    timing: MinorityFinishTiming,
    *,
    current_rule: RuleType,
) -> NormalFinishTransition:
    """Decide NORMAL-finish transition after a minority round (§8/§9).

    Only applies while the match is still judged under MINORITY. Once switched to
    NORMAL judging, pass ``current_rule=RuleType.NORMAL``.
    """
    if current_rule is not RuleType.MINORITY:
        return NormalFinishTransition(switch_now=False, defer_to_next_match=False)

    if survivor_count > threshold:
        return NormalFinishTransition(switch_now=False, defer_to_next_match=False)

    if timing is MinorityFinishTiming.IMMEDIATE:
        return NormalFinishTransition(switch_now=True, defer_to_next_match=False)

    return NormalFinishTransition(switch_now=False, defer_to_next_match=True)


def effective_judging_rule(
    match_rule_type: RuleType, *, switched_to_normal_finish: bool
) -> RuleType:
    """Rule used for the next round's judgment within a match."""
    if match_rule_type is RuleType.MINORITY and switched_to_normal_finish:
        return RuleType.NORMAL
    return match_rule_type
