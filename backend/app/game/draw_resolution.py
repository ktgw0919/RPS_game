"""Draw replay and post-round progression (ARCHITECTURE.md §8/§9).

Pure helpers shared by all rule types. A draw (same members replay) increments
``draw_round_count``; decisive rounds that change membership do not. When the
count reaches ``MatchConfig.max_draw_rounds`` the match ends with
``DRAW_MAX_ROUNDS``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.game.engine import RoundOutcome
from app.game.rules.boss_battle import BossRoundOutcome
from app.game.rules.minority import (
    effective_judging_rule,
    evaluate_normal_finish_transition,
)
from app.models import MatchConfig, MatchEndReason, NormalEndMode, RuleType


@dataclass(frozen=True)
class RoundProgression:
    """Outcome of applying a judged round to match state (pure, no side effects)."""

    alive_player_ids: tuple[str, ...]
    eliminated_player_ids: tuple[str, ...]
    draw_round_count: int
    match_ended: bool
    match_end_reason: MatchEndReason | None
    match_winner_ids: tuple[str, ...]
    score_deltas: tuple[tuple[str, int], ...] = ()
    switched_to_normal_finish: bool = False


def apply_draw_replay(
    draw_count: int,
    max_draw_rounds: int,
    alive_player_ids: Sequence[str],
) -> RoundProgression:
    """Handle a same-member draw: increment counter and maybe end the match (§8/§9)."""
    new_count = draw_count + 1
    if new_count >= max_draw_rounds:
        return RoundProgression(
            alive_player_ids=tuple(alive_player_ids),
            eliminated_player_ids=(),
            draw_round_count=new_count,
            match_ended=True,
            match_end_reason=MatchEndReason.DRAW_MAX_ROUNDS,
            match_winner_ids=(),
        )
    return RoundProgression(
        alive_player_ids=tuple(alive_player_ids),
        eliminated_player_ids=(),
        draw_round_count=new_count,
        match_ended=False,
        match_end_reason=None,
        match_winner_ids=(),
    )


def resolve_after_normal_round(
    outcome: RoundOutcome,
    alive_before: Sequence[str],
    draw_count: int,
    config: MatchConfig,
) -> RoundProgression:
    """Post-round progression for NORMAL (§8)."""
    if outcome.is_draw:
        return apply_draw_replay(draw_count, config.max_draw_rounds, alive_before)

    new_alive = outcome.winner_ids
    eliminated = outcome.eliminated_ids
    if config.normal_end_mode is NormalEndMode.SINGLE_ROUND:
        return RoundProgression(
            alive_player_ids=new_alive,
            eliminated_player_ids=eliminated,
            draw_round_count=draw_count,
            match_ended=True,
            match_end_reason=MatchEndReason.DECIDED,
            match_winner_ids=new_alive,
        )
    if len(new_alive) <= 1:
        return RoundProgression(
            alive_player_ids=new_alive,
            eliminated_player_ids=eliminated,
            draw_round_count=draw_count,
            match_ended=True,
            match_end_reason=MatchEndReason.DECIDED,
            match_winner_ids=new_alive,
        )
    return RoundProgression(
        alive_player_ids=new_alive,
        eliminated_player_ids=eliminated,
        draw_round_count=draw_count,
        match_ended=False,
        match_end_reason=None,
        match_winner_ids=(),
    )


def resolve_after_minority_round(
    outcome: RoundOutcome,
    alive_before: Sequence[str],
    draw_count: int,
    config: MatchConfig,
    *,
    switched_to_normal_finish: bool,
) -> RoundProgression:
    """Post-round progression for MINORITY (§8), including NORMAL-finish switch."""
    if outcome.is_draw:
        return apply_draw_replay(draw_count, config.max_draw_rounds, alive_before)

    new_alive = outcome.winner_ids
    eliminated = outcome.eliminated_ids
    transition = evaluate_normal_finish_transition(
        len(new_alive),
        config.minority_finish_threshold,
        config.minority_finish_timing,
        current_rule=RuleType.MINORITY,
    )
    now_normal = switched_to_normal_finish or transition.switch_now
    judging = effective_judging_rule(RuleType.MINORITY, switched_to_normal_finish=now_normal)

    if judging is RuleType.NORMAL:
        if len(new_alive) <= 1:
            return RoundProgression(
                alive_player_ids=new_alive,
                eliminated_player_ids=eliminated,
                draw_round_count=draw_count,
                match_ended=True,
                match_end_reason=MatchEndReason.DECIDED,
                match_winner_ids=new_alive,
                switched_to_normal_finish=now_normal,
            )
        if config.normal_end_mode is NormalEndMode.SINGLE_ROUND:
            return RoundProgression(
                alive_player_ids=new_alive,
                eliminated_player_ids=eliminated,
                draw_round_count=draw_count,
                match_ended=True,
                match_end_reason=MatchEndReason.DECIDED,
                match_winner_ids=new_alive,
                switched_to_normal_finish=now_normal,
            )

    if len(new_alive) <= 1:
        return RoundProgression(
            alive_player_ids=new_alive,
            eliminated_player_ids=eliminated,
            draw_round_count=draw_count,
            match_ended=True,
            match_end_reason=MatchEndReason.DECIDED,
            match_winner_ids=new_alive,
            switched_to_normal_finish=now_normal,
        )
    return RoundProgression(
        alive_player_ids=new_alive,
        eliminated_player_ids=eliminated,
        draw_round_count=draw_count,
        match_ended=False,
        match_end_reason=None,
        match_winner_ids=(),
        switched_to_normal_finish=now_normal,
    )


def resolve_after_boss_round(
    outcome: BossRoundOutcome,
    alive_before: Sequence[str],
    boss_player_id: str,
    draw_count: int,
    max_draw_rounds: int,
) -> RoundProgression:
    """Post-round progression for BOSS (§8). Boss ties count as elimination, not draw."""
    if outcome.is_draw:
        return apply_draw_replay(draw_count, max_draw_rounds, alive_before)

    alive_set = set(alive_before)
    winners = set(outcome.winner_ids)
    new_alive = tuple(pid for pid in alive_before if pid == boss_player_id or pid in winners)
    eliminated = tuple(pid for pid in alive_before if pid in alive_set and pid not in new_alive)

    participants_left = [pid for pid in new_alive if pid != boss_player_id]
    if len(participants_left) <= 1:
        return RoundProgression(
            alive_player_ids=new_alive,
            eliminated_player_ids=eliminated,
            draw_round_count=draw_count,
            match_ended=True,
            match_end_reason=MatchEndReason.DECIDED,
            match_winner_ids=tuple(participants_left),
            score_deltas=outcome.score_deltas,
        )
    return RoundProgression(
        alive_player_ids=new_alive,
        eliminated_player_ids=eliminated,
        draw_round_count=draw_count,
        match_ended=False,
        match_end_reason=None,
        match_winner_ids=(),
        score_deltas=outcome.score_deltas,
    )


@dataclass(frozen=True)
class TournamentPairProgression:
    """Progression for one tournament pair after judging (§8)."""

    replay_pair: bool
    pair_complete: bool
    winner_id: str | None
    draw_round_count: int
    match_ended: bool
    match_end_reason: MatchEndReason | None


def resolve_after_tournament_pair(
    outcome: RoundOutcome,
    pair_player_ids: Sequence[str],
    draw_count: int,
    max_draw_rounds: int,
) -> TournamentPairProgression:
    """Post-round progression for a single tournament pair (§8).

      Pair draws replay the same segment only; decisive results complete the pair.
    Match-wide ``max_draw_rounds`` applies to pair draws.
    """
    if outcome.is_draw:
        progressed = apply_draw_replay(draw_count, max_draw_rounds, pair_player_ids)
        return TournamentPairProgression(
            replay_pair=True,
            pair_complete=False,
            winner_id=None,
            draw_round_count=progressed.draw_round_count,
            match_ended=progressed.match_ended,
            match_end_reason=progressed.match_end_reason,
        )
    assert len(outcome.winner_ids) == 1
    return TournamentPairProgression(
        replay_pair=False,
        pair_complete=True,
        winner_id=outcome.winner_ids[0],
        draw_round_count=draw_count,
        match_ended=False,
        match_end_reason=None,
    )


def should_count_draw(
    outcome_is_draw: bool, alive_before: Sequence[str], alive_after: Sequence[str]
) -> bool:
    """True when a round increments ``draw_round_count`` (§8 same-member replay)."""
    if not outcome_is_draw:
        return False
    return tuple(alive_before) == tuple(alive_after)
