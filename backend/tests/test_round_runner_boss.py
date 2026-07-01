"""RoundRunner BOSS integration tests (TODO Step R3)."""

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


def _boss_setup(
    boss_id: str,
    participant_ids: list[str],
    *,
    advance: RoundAdvanceMode = RoundAdvanceMode.MANUAL,
) -> tuple[RoundRunner, InMemoryGameStateStore, Any, Any]:
    ids = [boss_id, *participant_ids]
    store = InMemoryGameStateStore()
    runner = RoundRunner(store, ConnectionManager(), now=lambda: NOW, result_delay_sleep=_never)
    room = store.create_room(_player(ids[0]))
    for pid in ids[1:]:
        store.add_player(room, _player(pid))
    store.set_config(
        room,
        MatchConfig(
            rule_type=RuleType.BOSS,
            boss_player_id=boss_id,
            round_advance_mode=advance,
        ),
    )
    match = store.start_match(
        room, alive_player_ids=ids, config=room.config, match_id="m-boss", now=NOW
    )
    store.begin_round(match, round_no=1, deadline_at=NOW)
    return runner, store, room, match


@pytest.mark.asyncio
async def test_boss_round_eliminates_losers_and_scores_winner() -> None:
    """Boss ROCK: participant beating boss survives with +1 score (§8)."""
    runner, store, room, match = _boss_setup("boss", ["p1", "p2"])
    store.save_submission(match, "boss", Hand.ROCK)
    store.save_submission(match, "p1", Hand.PAPER)
    store.save_submission(match, "p2", Hand.SCISSORS)

    await runner._resolve_round(room, None, 1)

    assert match.alive_player_ids == ["boss", "p1"]
    assert match.scores == {"p1": 1}
    assert match.state is MatchState.MATCH_END
    assert match.winner_ids == ["p1"]


@pytest.mark.asyncio
async def test_boss_missing_hand_triggers_safety_draw() -> None:
    runner, store, room, match = _boss_setup("boss", ["p1", "p2"])
    store.save_submission(match, "p1", Hand.ROCK)
    store.save_submission(match, "p2", Hand.PAPER)

    await runner._resolve_round(room, None, 1)

    assert match.alive_player_ids == ["boss", "p1", "p2"]
    assert match.draw_round_count == 1
    assert match.state is MatchState.ROUND_RESULT


@pytest.mark.asyncio
async def test_boss_all_participants_lose_is_safety_draw() -> None:
    runner, store, room, match = _boss_setup("boss", ["p1", "p2"])
    store.save_submission(match, "boss", Hand.ROCK)
    store.save_submission(match, "p1", Hand.SCISSORS)
    store.save_submission(match, "p2", Hand.SCISSORS)

    await runner._resolve_round(room, None, 1)

    assert match.alive_player_ids == ["boss", "p1", "p2"]
    assert match.draw_round_count == 1
    assert match.scores == {}
