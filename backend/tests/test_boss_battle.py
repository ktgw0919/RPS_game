"""BOSS judgment engine unit tests (ARCHITECTURE.md §8, Phase 3 Step 2).

Pure functions only: no store, sockets, or clock.
"""

from __future__ import annotations

import pytest

from app.game.rules.boss_battle import (
    BossRoundOutcome,
    boss_start_ok,
    judge_boss_round,
    min_players_for_boss,
    participant_ids,
)
from app.models import Hand

BOSS = "boss"
P1 = "p1"
P2 = "p2"
P3 = "p3"


@pytest.mark.parametrize(
    ("player", "boss_hand", "winning"),
    [
        (Hand.ROCK, Hand.SCISSORS, True),
        (Hand.SCISSORS, Hand.PAPER, True),
        (Hand.PAPER, Hand.ROCK, True),
        (Hand.ROCK, Hand.PAPER, False),
        (Hand.ROCK, Hand.ROCK, False),
    ],
)
def test_participant_vs_boss(player: Hand, boss_hand: Hand, winning: bool) -> None:
    outcome = judge_boss_round(
        [BOSS, P1],
        BOSS,
        boss_hand,
        {BOSS: boss_hand, P1: player},
    )
    if winning:
        assert outcome == BossRoundOutcome(
            is_draw=False,
            winner_ids=(P1,),
            eliminated_ids=(),
            score_deltas=((P1, 1),),
        )
    elif player == boss_hand:
        assert outcome.is_draw is True
    else:
        assert outcome.is_draw is True


def test_tie_with_boss_eliminates_participant() -> None:
    outcome = judge_boss_round(
        [BOSS, P1, P2],
        BOSS,
        Hand.ROCK,
        {BOSS: Hand.ROCK, P1: Hand.ROCK, P2: Hand.PAPER},
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == (P2,)
    assert outcome.eliminated_ids == (P1,)
    assert outcome.score_deltas == ((P2, 1),)


def test_mixed_win_and_loss() -> None:
    outcome = judge_boss_round(
        [BOSS, P1, P2, P3],
        BOSS,
        Hand.ROCK,
        {
            BOSS: Hand.ROCK,
            P1: Hand.PAPER,
            P2: Hand.SCISSORS,
            P3: Hand.ROCK,
        },
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == (P1,)
    assert outcome.eliminated_ids == (P2, P3)
    assert outcome.score_deltas == ((P1, 1),)


def test_multiple_winners_gain_score() -> None:
    outcome = judge_boss_round(
        [BOSS, P1, P2],
        BOSS,
        Hand.SCISSORS,
        {BOSS: Hand.SCISSORS, P1: Hand.ROCK, P2: Hand.ROCK},
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == (P1, P2)
    assert outcome.eliminated_ids == ()
    assert outcome.score_deltas == ((P1, 1), (P2, 1))


def test_non_submitter_eliminated() -> None:
    outcome = judge_boss_round(
        [BOSS, P1, P2],
        BOSS,
        Hand.SCISSORS,
        {BOSS: Hand.SCISSORS, P1: Hand.ROCK},
    )
    assert outcome.is_draw is False
    assert outcome.winner_ids == (P1,)
    assert outcome.eliminated_ids == (P2,)


def test_no_participant_submissions_is_draw() -> None:
    outcome = judge_boss_round([BOSS, P1], BOSS, Hand.ROCK, {BOSS: Hand.ROCK})
    assert outcome.is_draw is True
    assert outcome.winner_ids == ()
    assert outcome.eliminated_ids == ()
    assert outcome.score_deltas == ()


def test_all_participants_lose_or_tie_is_draw() -> None:
    # Boss ROCK: both participants lose -> §7 zero survivors -> draw.
    outcome = judge_boss_round(
        [BOSS, P1, P2],
        BOSS,
        Hand.ROCK,
        {BOSS: Hand.ROCK, P1: Hand.SCISSORS, P2: Hand.SCISSORS},
    )
    assert outcome.is_draw is True


def test_boss_never_in_outcome_ids() -> None:
    outcome = judge_boss_round(
        [BOSS, P1],
        BOSS,
        Hand.SCISSORS,
        {BOSS: Hand.SCISSORS, P1: Hand.ROCK},
    )
    assert BOSS not in outcome.winner_ids
    assert BOSS not in outcome.eliminated_ids
    assert all(pid != BOSS for pid, _ in outcome.score_deltas)


def test_submissions_from_non_alive_ignored() -> None:
    outcome = judge_boss_round(
        [BOSS, P1],
        BOSS,
        Hand.SCISSORS,
        {BOSS: Hand.SCISSORS, P1: Hand.ROCK, "ghost": Hand.PAPER},
    )
    assert outcome.winner_ids == (P1,)


def test_participant_ids_excludes_boss() -> None:
    assert participant_ids([BOSS, P1, P2], BOSS) == (P1, P2)


def test_boss_start_ok_requires_boss_and_participant() -> None:
    assert min_players_for_boss() == 2
    assert boss_start_ok([BOSS, P1], BOSS) is True
    assert boss_start_ok([P1, P2], BOSS) is False
    assert boss_start_ok([BOSS], BOSS) is False
    assert boss_start_ok([BOSS, P1], None) is False
