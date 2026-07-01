"""Draw replay and post-round progression unit tests (Phase 3 Step 4)."""

from __future__ import annotations

import pytest

from app.game.draw_resolution import (
    RoundProgression,
    apply_draw_replay,
    resolve_after_boss_round,
    resolve_after_minority_round,
    resolve_after_normal_round,
    resolve_after_tournament_pair,
    should_count_draw,
)
from app.game.engine import RoundOutcome
from app.game.rules.boss_battle import BossRoundOutcome
from app.models import MatchConfig, MatchEndReason, MinorityFinishTiming, NormalEndMode

A, B, C = "a", "b", "c"
BOSS = "boss"


def test_apply_draw_replay_under_cap() -> None:
    result = apply_draw_replay(0, max_draw_rounds=5, alive_player_ids=[A, B])
    assert result == RoundProgression(
        alive_player_ids=(A, B),
        eliminated_player_ids=(),
        draw_round_count=1,
        match_ended=False,
        match_end_reason=None,
        match_winner_ids=(),
    )


def test_apply_draw_replay_at_cap_ends_match() -> None:
    result = apply_draw_replay(4, max_draw_rounds=5, alive_player_ids=[A, B])
    assert result.match_ended is True
    assert result.match_end_reason is MatchEndReason.DRAW_MAX_ROUNDS
    assert result.draw_round_count == 5
    assert result.match_winner_ids == ()


def test_normal_draw_replays_without_elimination() -> None:
    outcome = RoundOutcome(is_draw=True)
    result = resolve_after_normal_round(outcome, [A, B], draw_count=0, config=MatchConfig())
    assert result.eliminated_player_ids == ()
    assert result.alive_player_ids == (A, B)
    assert result.draw_round_count == 1
    assert result.match_ended is False


def test_normal_decisive_elimination_does_not_increment_draw() -> None:
    outcome = RoundOutcome(is_draw=False, winner_ids=(A,), eliminated_ids=(B,))
    result = resolve_after_normal_round(
        outcome,
        [A, B],
        draw_count=2,
        config=MatchConfig(normal_end_mode=NormalEndMode.ELIMINATION),
    )
    assert result.draw_round_count == 2
    assert result.alive_player_ids == (A,)
    assert result.match_ended is True
    assert result.match_winner_ids == (A,)


def test_normal_single_round_ends_on_first_decisive() -> None:
    outcome = RoundOutcome(is_draw=False, winner_ids=(A,), eliminated_ids=(B,))
    result = resolve_after_normal_round(
        outcome,
        [A, B, C],
        draw_count=0,
        config=MatchConfig(normal_end_mode=NormalEndMode.SINGLE_ROUND),
    )
    assert result.match_ended is True
    assert result.match_winner_ids == (A,)


def test_minority_draw_increments_draw_count() -> None:
    outcome = RoundOutcome(is_draw=True)
    result = resolve_after_minority_round(
        outcome, [A, B, C], draw_count=0, config=MatchConfig(), switched_to_normal_finish=False
    )
    assert result.draw_round_count == 1
    assert result.alive_player_ids == (A, B, C)


def test_minority_decisive_does_not_increment_draw() -> None:
    outcome = RoundOutcome(is_draw=False, winner_ids=(A,), eliminated_ids=(B, C))
    result = resolve_after_minority_round(
        outcome,
        [A, B, C],
        draw_count=3,
        config=MatchConfig(minority_finish_threshold=2),
        switched_to_normal_finish=False,
    )
    assert result.draw_round_count == 3
    assert result.alive_player_ids == (A,)


def test_minority_switches_to_normal_finish_at_threshold() -> None:
    outcome = RoundOutcome(is_draw=False, winner_ids=(A, B), eliminated_ids=(C,))
    result = resolve_after_minority_round(
        outcome,
        [A, B, C],
        draw_count=0,
        config=MatchConfig(
            minority_finish_threshold=2,
            minority_finish_timing=MinorityFinishTiming.IMMEDIATE,
            normal_end_mode=NormalEndMode.ELIMINATION,
        ),
        switched_to_normal_finish=False,
    )
    assert result.switched_to_normal_finish is True
    assert result.match_ended is False


def test_boss_safety_draw_increments_draw_count() -> None:
    outcome = BossRoundOutcome(is_draw=True)
    result = resolve_after_boss_round(outcome, [BOSS, A, B], BOSS, draw_count=0, max_draw_rounds=5)
    assert result.draw_round_count == 1
    assert result.alive_player_ids == (BOSS, A, B)


def test_boss_decisive_eliminates_without_draw_increment() -> None:
    outcome = BossRoundOutcome(
        is_draw=False,
        winner_ids=(A,),
        eliminated_ids=(B,),
        score_deltas=((A, 1),),
    )
    result = resolve_after_boss_round(outcome, [BOSS, A, B], BOSS, draw_count=2, max_draw_rounds=5)
    assert result.draw_round_count == 2
    assert result.alive_player_ids == (BOSS, A)
    assert result.score_deltas == ((A, 1),)
    assert result.match_ended is True
    assert result.match_winner_ids == (A,)


def test_tournament_pair_draw_replays_segment() -> None:
    outcome = RoundOutcome(is_draw=True)
    result = resolve_after_tournament_pair(outcome, [A, B], draw_count=0, max_draw_rounds=3)
    assert result.replay_pair is True
    assert result.pair_complete is False
    assert result.draw_round_count == 1


def test_tournament_pair_draw_cap_ends_match() -> None:
    outcome = RoundOutcome(is_draw=True)
    result = resolve_after_tournament_pair(outcome, [A, B], draw_count=2, max_draw_rounds=3)
    assert result.match_ended is True
    assert result.match_end_reason is MatchEndReason.DRAW_MAX_ROUNDS


def test_tournament_pair_decisive_completes_pair() -> None:
    outcome = RoundOutcome(is_draw=False, winner_ids=(A,), eliminated_ids=(B,))
    result = resolve_after_tournament_pair(outcome, [A, B], draw_count=1, max_draw_rounds=5)
    assert result.pair_complete is True
    assert result.winner_id == A
    assert result.draw_round_count == 1


@pytest.mark.parametrize(
    ("is_draw", "before", "after", "expected"),
    [
        (True, (A, B), (A, B), True),
        (True, (A, B), (A,), False),
        (False, (A, B), (A,), False),
    ],
)
def test_should_count_draw(
    is_draw: bool, before: tuple[str, ...], after: tuple[str, ...], expected: bool
) -> None:
    assert should_count_draw(is_draw, before, after) is expected
