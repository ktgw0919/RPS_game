"""MINORITY judgment engine unit tests (ARCHITECTURE.md §8, Phase 3 Step 1).

Pure functions only: no store, sockets, or clock.
"""

from __future__ import annotations

import pytest

from app.game.rules.minority import (
    NormalFinishTransition,
    effective_judging_rule,
    evaluate_normal_finish_transition,
    judge_minority_round,
)
from app.models import Hand, MinorityFinishTiming, RuleType


def test_unique_minority_hand_survives() -> None:
    # ROCK=2, PAPER=1 (minority), SCISSORS=2 -> only PAPER submitter survives.
    outcome = judge_minority_round(
        ["a", "b", "c", "d", "e"],
        {
            "a": Hand.ROCK,
            "b": Hand.ROCK,
            "c": Hand.PAPER,
            "d": Hand.SCISSORS,
            "e": Hand.SCISSORS,
        },
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == ("c",)
    assert outcome.eliminated_ids == ("a", "b", "d", "e")


def test_tied_minimum_hands_is_draw() -> None:
    # ROCK=1, PAPER=1, SCISSORS=3 -> two hands tie for minimum.
    outcome = judge_minority_round(
        ["a", "b", "c", "d", "e"],
        {
            "a": Hand.ROCK,
            "b": Hand.PAPER,
            "c": Hand.SCISSORS,
            "d": Hand.SCISSORS,
            "e": Hand.SCISSORS,
        },
    )
    assert outcome.is_draw is True
    assert outcome.winner_ids == ()
    assert outcome.eliminated_ids == ()


def test_all_same_hand_is_draw() -> None:
    for hand in Hand:
        outcome = judge_minority_round(["a", "b", "c"], {"a": hand, "b": hand, "c": hand})
        assert outcome.is_draw is True


def test_three_kinds_each_once_is_draw() -> None:
    outcome = judge_minority_round(
        ["a", "b", "c"],
        {"a": Hand.ROCK, "b": Hand.PAPER, "c": Hand.SCISSORS},
    )
    assert outcome.is_draw is True


def test_non_submitter_eliminated_in_decisive_round() -> None:
    # ROCK=3, PAPER=1 -> PAPER wins; non-submitter loses.
    outcome = judge_minority_round(
        ["a", "b", "c", "d", "e"],
        {
            "a": Hand.ROCK,
            "b": Hand.ROCK,
            "c": Hand.ROCK,
            "d": Hand.PAPER,
        },
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == ("d",)
    assert outcome.eliminated_ids == ("a", "b", "c", "e")


def test_non_submitters_not_eliminated_when_draw() -> None:
    # Only ROCK submitted -> all same -> draw.
    outcome = judge_minority_round(["a", "b"], {"a": Hand.ROCK})
    assert outcome.is_draw is True
    assert outcome.eliminated_ids == ()


def test_no_submissions_is_draw() -> None:
    outcome = judge_minority_round(["a", "b", "c"], {})
    assert outcome.is_draw is True


def test_submissions_from_non_alive_are_ignored() -> None:
    outcome = judge_minority_round(
        ["a", "b"],
        {"a": Hand.ROCK, "b": Hand.PAPER, "ghost": Hand.SCISSORS},
    )
    assert outcome.is_draw is True


def test_multiple_minority_submitters_survive() -> None:
    # ROCK=3, PAPER=2 (minority) -> both PAPER players survive.
    outcome = judge_minority_round(
        ["a", "b", "c", "d", "e"],
        {
            "a": Hand.ROCK,
            "b": Hand.ROCK,
            "c": Hand.ROCK,
            "d": Hand.PAPER,
            "e": Hand.PAPER,
        },
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == ("d", "e")
    assert outcome.eliminated_ids == ("a", "b", "c")


@pytest.mark.parametrize(
    ("survivors", "threshold", "timing", "expected"),
    [
        (
            3,
            2,
            MinorityFinishTiming.IMMEDIATE,
            NormalFinishTransition(switch_now=False, defer_to_next_match=False),
        ),
        (
            2,
            2,
            MinorityFinishTiming.IMMEDIATE,
            NormalFinishTransition(switch_now=True, defer_to_next_match=False),
        ),
        (
            1,
            2,
            MinorityFinishTiming.IMMEDIATE,
            NormalFinishTransition(switch_now=True, defer_to_next_match=False),
        ),
        (
            2,
            2,
            MinorityFinishTiming.NEXT_MATCH,
            NormalFinishTransition(switch_now=False, defer_to_next_match=True),
        ),
        (
            3,
            2,
            MinorityFinishTiming.NEXT_MATCH,
            NormalFinishTransition(switch_now=False, defer_to_next_match=False),
        ),
    ],
)
def test_normal_finish_transition(
    survivors: int,
    threshold: int,
    timing: MinorityFinishTiming,
    expected: NormalFinishTransition,
) -> None:
    result = evaluate_normal_finish_transition(
        survivors,
        threshold,
        timing,
        current_rule=RuleType.MINORITY,
    )
    assert result == expected


def test_normal_finish_transition_ignored_when_already_normal() -> None:
    result = evaluate_normal_finish_transition(
        2,
        2,
        MinorityFinishTiming.IMMEDIATE,
        current_rule=RuleType.NORMAL,
    )
    assert result == NormalFinishTransition(switch_now=False, defer_to_next_match=False)


@pytest.mark.parametrize(
    ("match_rule", "switched", "expected"),
    [
        (RuleType.MINORITY, False, RuleType.MINORITY),
        (RuleType.MINORITY, True, RuleType.NORMAL),
        (RuleType.NORMAL, False, RuleType.NORMAL),
        (RuleType.NORMAL, True, RuleType.NORMAL),
    ],
)
def test_effective_judging_rule(match_rule: RuleType, switched: bool, expected: RuleType) -> None:
    assert effective_judging_rule(match_rule, switched_to_normal_finish=switched) is expected
