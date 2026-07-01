"""RoundRunner unit tests (ARCHITECTURE.md §7.1).

Exercises judge-exactly-once and stale-timer no-op paths directly on
`RoundRunner._resolve_round` with injected `now`/sleep — no WebSocket, no wall
clock. Complements `test_ws_round.py` integration coverage.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.connection_manager import ConnectionManager
from app.core.round_runner import RoundRunner
from app.core.state_store import InMemoryGameStateStore
from app.models import Hand, MatchConfig, MatchState, Player, RoundAdvanceMode

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _never(_seconds: float) -> None:
    await asyncio.Event().wait()


def _player(pid: str, **kwargs: Any) -> Player:
    kwargs.setdefault("token", f"tok-{pid}")
    return Player(player_id=pid, display_name=pid, joined_at=NOW, **kwargs)


def _room_with_collecting_round() -> tuple[RoundRunner, InMemoryGameStateStore, Any, Any]:
    store = InMemoryGameStateStore()
    runner = RoundRunner(store, ConnectionManager(), now=lambda: NOW, result_delay_sleep=_never)
    room = store.create_room(_player("a"))
    store.add_player(room, _player("b"))
    store.set_config(room, MatchConfig(round_advance_mode=RoundAdvanceMode.MANUAL))
    match = store.start_match(
        room, alive_player_ids=["a", "b"], config=room.config, match_id="m1", now=NOW
    )
    store.begin_round(match, round_no=1, deadline_at=NOW)
    return runner, store, room, match


@pytest.mark.asyncio
async def test_resolve_round_second_call_is_noop() -> None:
    """Late `_resolve_round` after a finished judge must not re-judge (§7.1)."""
    runner, store, room, match = _room_with_collecting_round()
    store.save_submission(match, "a", Hand.ROCK)
    store.save_submission(match, "b", Hand.ROCK)  # draw -> stays at ROUND_RESULT (MANUAL)

    await runner._resolve_round(room, None, 1)
    judged_at = match.current_round.judged_at
    assert judged_at == NOW
    assert match.state is MatchState.ROUND_RESULT

    await runner._resolve_round(room, None, 1)
    assert match.current_round.judged_at == judged_at
    assert match.state is MatchState.ROUND_RESULT


@pytest.mark.asyncio
async def test_resolve_round_stale_round_no_is_noop() -> None:
    """A timer for an older `round_no` must not judge the current round (§7.1)."""
    runner, store, room, match = _room_with_collecting_round()
    store.save_submission(match, "a", Hand.ROCK)

    await runner._resolve_round(room, None, 0)  # stale expected_round_no

    assert match.state is MatchState.COLLECTING
    assert match.current_round is not None
    assert match.current_round.judged_at is None


@pytest.mark.asyncio
async def test_deadline_timer_after_early_finish_is_noop() -> None:
    """A deadline wake after judge must not produce a second outcome (§7.1)."""
    runner, store, room, match = _room_with_collecting_round()
    store.save_submission(match, "a", Hand.ROCK)
    store.save_submission(match, "b", Hand.ROCK)

    runner._cancel_key((room.room_code.upper(), None))
    await runner._resolve_round(room, None, 1)
    assert match.state is MatchState.ROUND_RESULT

    await runner._deadline_timer(room, None, round_no=1, seconds=0.0)
    assert match.state is MatchState.ROUND_RESULT
    assert match.current_round.judged_at == NOW


@pytest.mark.asyncio
async def test_auto_advance_waits_result_display_before_next_round() -> None:
    """AUTO mode blocks on `result_display_sec` before opening the next round (§6/§9)."""
    released = asyncio.Event()

    async def gated(_seconds: float) -> None:
        await released.wait()

    store = InMemoryGameStateStore()
    runner = RoundRunner(
        store,
        ConnectionManager(),
        now=lambda: NOW,
        result_delay_sleep=gated,
    )
    room = store.create_room(_player("a"))
    store.add_player(room, _player("b"))
    store.set_config(room, MatchConfig(round_advance_mode=RoundAdvanceMode.AUTO))
    match = store.start_match(
        room, alive_player_ids=["a", "b"], config=room.config, match_id="m1", now=NOW
    )
    store.begin_round(match, round_no=1, deadline_at=NOW)
    store.save_submission(match, "a", Hand.ROCK)
    store.save_submission(match, "b", Hand.ROCK)

    task = asyncio.create_task(runner._resolve_round(room, None, 1))
    await asyncio.sleep(0.05)
    assert match.state is MatchState.ROUND_RESULT
    assert match.current_round_no == 1

    released.set()
    await task
    assert match.state is MatchState.COLLECTING
    assert match.current_round_no == 2
