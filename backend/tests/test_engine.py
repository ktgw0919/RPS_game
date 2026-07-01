"""NORMAL judgment engine unit tests (ARCHITECTURE.md §8, Phase 2 Step 8).

The engine is pure: these tests need no store, sockets, or clock.
"""

from __future__ import annotations

import pytest

from app.game.engine import judge_normal_round
from app.models import Hand

# (winning hand, losing hand) for every RPS pair.
_WINS = [
    (Hand.ROCK, Hand.SCISSORS),
    (Hand.SCISSORS, Hand.PAPER),
    (Hand.PAPER, Hand.ROCK),
]


@pytest.mark.parametrize(("winning", "losing"), _WINS)
def test_two_players_decisive(winning: Hand, losing: Hand) -> None:
    outcome = judge_normal_round(["a", "b"], {"a": winning, "b": losing})
    assert outcome.is_draw is False
    assert outcome.winner_ids == ("a",)
    assert outcome.eliminated_ids == ("b",)


def test_all_same_hand_is_draw() -> None:
    for hand in Hand:
        outcome = judge_normal_round(["a", "b", "c"], {"a": hand, "b": hand, "c": hand})
        assert outcome.is_draw is True
        assert outcome.winner_ids == ()
        assert outcome.eliminated_ids == ()


def test_three_kinds_is_draw() -> None:
    outcome = judge_normal_round(
        ["a", "b", "c"], {"a": Hand.ROCK, "b": Hand.SCISSORS, "c": Hand.PAPER}
    )
    assert outcome.is_draw is True


def test_multi_player_two_kinds() -> None:
    # ROCK beats SCISSORS: the two ROCK players survive, the SCISSORS one is out.
    outcome = judge_normal_round(
        ["a", "b", "c"], {"a": Hand.ROCK, "b": Hand.ROCK, "c": Hand.SCISSORS}
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == ("a", "b")
    assert outcome.eliminated_ids == ("c",)


def test_non_submitter_is_eliminated_in_decisive_round() -> None:
    # §7: an alive player who did not submit loses a decisive round.
    outcome = judge_normal_round(["a", "b", "c"], {"a": Hand.ROCK, "b": Hand.SCISSORS})
    assert outcome.is_draw is False
    assert outcome.winner_ids == ("a",)
    assert outcome.eliminated_ids == ("b", "c")


def test_non_submitters_not_eliminated_when_draw() -> None:
    # Only one hand appeared -> §8 draw -> nobody (incl. non-submitter) is out.
    outcome = judge_normal_round(["a", "b"], {"a": Hand.ROCK})
    assert outcome.is_draw is True
    assert outcome.eliminated_ids == ()


def test_no_submissions_is_draw() -> None:
    outcome = judge_normal_round(["a", "b"], {})
    assert outcome.is_draw is True


def test_submissions_from_non_alive_are_ignored() -> None:
    # A stray submission from a non-alive id must not affect the result.
    outcome = judge_normal_round(["a"], {"a": Hand.ROCK, "ghost": Hand.SCISSORS})
    assert outcome.is_draw is True
