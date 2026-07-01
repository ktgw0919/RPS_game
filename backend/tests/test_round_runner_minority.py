"""RoundRunner MINORITY integration tests (TODO Step R2)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.connection_manager import ConnectionManager
from app.core.round_runner import RoundRunner
from app.core.state_store import InMemoryGameStateStore
from app.models import (
    Hand,
    MatchConfig,
    MatchState,
    MinorityFinishTiming,
    NormalEndMode,
    Player,
    RoundAdvanceMode,
    RuleType,
)

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _never(_seconds: float) -> None:
    await asyncio.Event().wait()


def _player(pid: str, **kwargs: Any) -> Player:
    kwargs.setdefault("token", f"tok-{pid}")
    return Player(player_id=pid, display_name=pid, joined_at=NOW, **kwargs)


def _minority_setup(
    ids: list[str],
    *,
    threshold: int = 2,
    timing: MinorityFinishTiming = MinorityFinishTiming.IMMEDIATE,
    advance: RoundAdvanceMode = RoundAdvanceMode.MANUAL,
) -> tuple[RoundRunner, InMemoryGameStateStore, Any, Any]:
    store = InMemoryGameStateStore()
    runner = RoundRunner(store, ConnectionManager(), now=lambda: NOW, result_delay_sleep=_never)
    room = store.create_room(_player(ids[0]))
    for pid in ids[1:]:
        store.add_player(room, _player(pid))
    store.set_config(
        room,
        MatchConfig(
            rule_type=RuleType.MINORITY,
            minority_finish_threshold=threshold,
            minority_finish_timing=timing,
            normal_end_mode=NormalEndMode.ELIMINATION,
            round_advance_mode=advance,
        ),
    )
    match = store.start_match(
        room, alive_player_ids=ids, config=room.config, match_id="m-min", now=NOW
    )
    store.begin_round(match, round_no=1, deadline_at=NOW)
    return runner, store, room, match


@pytest.mark.asyncio
async def test_minority_round_eliminates_non_minority_hands() -> None:
    """Three players: unique minority hand survives (§8)."""
    runner, _store, room, match = _minority_setup(["a", "b", "c"])
    store = runner._store
    store.save_submission(match, "a", Hand.ROCK)
    store.save_submission(match, "b", Hand.ROCK)
    store.save_submission(match, "c", Hand.PAPER)

    await runner._resolve_round(room, None, 1)

    assert match.alive_player_ids == ["c"]
    assert match.state is MatchState.MATCH_END
    assert match.winner_ids == ["c"]


@pytest.mark.asyncio
async def test_minority_switches_to_normal_finish_at_threshold() -> None:
    """Seven players -> two survivors triggers IMMEDIATE NORMAL finish (§8/§9)."""
    ids = [f"p{i}" for i in range(7)]
    runner, _store, room, match = _minority_setup(ids, threshold=2)
    store = runner._store
    for pid in ids[:5]:
        store.save_submission(match, pid, Hand.ROCK)
    store.save_submission(match, "p5", Hand.PAPER)
    store.save_submission(match, "p6", Hand.PAPER)

    await runner._resolve_round(room, None, 1)

    assert match.alive_player_ids == ["p5", "p6"]
    assert match.switched_to_normal_finish is True
    assert match.state is MatchState.ROUND_RESULT


@pytest.mark.asyncio
async def test_after_normal_switch_uses_normal_judging() -> None:
    """Post-threshold round uses NORMAL RPS (§8)."""
    runner, _store, room, match = _minority_setup(["a", "b"], threshold=2)
    store = runner._store
    match.switched_to_normal_finish = True
    store.save_submission(match, "a", Hand.ROCK)
    store.save_submission(match, "b", Hand.SCISSORS)

    await runner._resolve_round(room, None, 1)

    assert match.alive_player_ids == ["a"]
    assert match.state is MatchState.MATCH_END
    assert match.winner_ids == ["a"]


@pytest.mark.asyncio
async def test_minority_next_match_sets_defer_flag() -> None:
    ids = ["a", "b", "c"]
    runner, _store, room, match = _minority_setup(
        ids, threshold=2, timing=MinorityFinishTiming.NEXT_MATCH
    )
    store = runner._store
    store.save_submission(match, "a", Hand.ROCK)
    store.save_submission(match, "b", Hand.ROCK)
    store.save_submission(match, "c", Hand.PAPER)

    await runner._resolve_round(room, None, 1)

    assert match.alive_player_ids == ["c"]
    assert match.switched_to_normal_finish is False
    assert match.minority_defer_normal_next_match is True
