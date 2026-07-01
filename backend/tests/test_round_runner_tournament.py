"""RoundRunner TOURNAMENT integration tests (TODO Step R4)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.connection_manager import ConnectionManager
from app.core.round_runner import RoundRunner
from app.core.state_store import InMemoryGameStateStore
from app.models import Hand, MatchConfig, MatchState, Player, RoundAdvanceMode, RuleType

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _never(_seconds: float) -> None:
    await asyncio.Event().wait()


def _player(pid: str, **kwargs: Any) -> Player:
    kwargs.setdefault("token", f"tok-{pid}")
    return Player(player_id=pid, display_name=pid, joined_at=NOW, **kwargs)


def _tournament_setup(
    ids: list[str],
    *,
    advance: RoundAdvanceMode = RoundAdvanceMode.MANUAL,
) -> tuple[RoundRunner, InMemoryGameStateStore, Any, Any]:
    store = InMemoryGameStateStore()
    runner = RoundRunner(store, ConnectionManager(), now=lambda: NOW, result_delay_sleep=_never)
    room = store.create_room(_player(ids[0]))
    for pid in ids[1:]:
        store.add_player(room, _player(pid))
    store.set_config(
        room,
        MatchConfig(rule_type=RuleType.TOURNAMENT, round_advance_mode=advance),
    )
    match = store.start_match(
        room, alive_player_ids=ids, config=room.config, match_id="m-t", now=NOW
    )
    return runner, store, room, match


@pytest.mark.asyncio
async def test_tournament_stage_starts_parallel_segments() -> None:
    runner, _store, room, match = _tournament_setup(["a", "b", "c", "d"])
    await runner._start_tournament_stage(room)

    assert match.current_round_no == 1
    assert set(match.tournament_segment_rounds) == {"r0-p0", "r0-p1"}
    assert match.tournament_segment_rounds["r0-p0"].round_no == 1
    assert match.state is MatchState.COLLECTING


@pytest.mark.asyncio
async def test_tournament_four_players_produces_champion() -> None:
    runner, store, room, match = _tournament_setup(["a", "b", "c", "d"])
    await runner._start_tournament_stage(room)

    store.save_segment_submission(match, "r0-p0", "a", Hand.ROCK)
    store.save_segment_submission(match, "r0-p0", "b", Hand.SCISSORS)
    await runner._resolve_round(room, "r0-p0", 1)

    store.save_segment_submission(match, "r0-p1", "c", Hand.PAPER)
    store.save_segment_submission(match, "r0-p1", "d", Hand.ROCK)
    await runner._resolve_round(room, "r0-p1", 1)

    assert match.state is MatchState.ROUND_RESULT
    assert match.tournament_segment_winners == {}

    await runner._start_tournament_stage(room)
    store.save_segment_submission(match, "r1-p0", "a", Hand.ROCK)
    store.save_segment_submission(match, "r1-p0", "c", Hand.SCISSORS)
    await runner._resolve_round(room, "r1-p0", 2)

    assert match.state is MatchState.MATCH_END
    assert match.winner_ids == ["a"]


@pytest.mark.asyncio
async def test_tournament_pair_draw_replays_segment() -> None:
    runner, store, room, match = _tournament_setup(["a", "b", "c", "d"])
    await runner._start_tournament_stage(room)

    store.save_segment_submission(match, "r0-p0", "a", Hand.ROCK)
    store.save_segment_submission(match, "r0-p0", "b", Hand.ROCK)
    await runner._resolve_round(room, "r0-p0", 1)

    replay = match.tournament_segment_rounds["r0-p0"]
    assert replay.round_no == 2
    assert match.tournament_segment_draw_counts["r0-p0"] == 1
    assert match.state is MatchState.COLLECTING


@pytest.mark.asyncio
async def test_tournament_three_players_bye_advances_without_round() -> None:
    runner, _store, room, match = _tournament_setup(["a", "b", "c"])
    assert match.tournament_segment_winners == {"r0-p1": "c"}

    await runner._start_tournament_stage(room)
    assert set(match.tournament_segment_rounds) == {"r0-p0"}

    store = runner._store
    store.save_segment_submission(match, "r0-p0", "a", Hand.ROCK)
    store.save_segment_submission(match, "r0-p0", "b", Hand.SCISSORS)
    await runner._resolve_round(room, "r0-p0", 1)

    assert match.state is MatchState.ROUND_RESULT
    await runner._start_tournament_stage(room)
    assert len(match.tournament_active_pairs) == 1
    assert match.tournament_active_pairs[0].players == ("a", "c")
    assert match.tournament_segment_winners == {}
