"""Start-condition (set S) unit tests (ARCHITECTURE.md §4.2, Phase 2 Step 6)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.state_store import InMemoryGameStateStore
from app.game.start_conditions import can_start, eligible_player_ids, min_players_for
from app.models import ConnectionState, CpuStrategy, Player, RuleType

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _player(pid: str, **kwargs: Any) -> Player:
    kwargs.setdefault("token", f"tok-{pid}")
    return Player(player_id=pid, display_name=pid, joined_at=NOW, **kwargs)


def _store_with_host() -> tuple[InMemoryGameStateStore, Any]:
    store = InMemoryGameStateStore()
    return store, store.create_room(_player("h"))


def test_eligible_excludes_spectators_and_disconnected() -> None:
    store, room = _store_with_host()
    store.add_player(room, _player("spec", is_spectator=True))
    store.add_player(room, _player("down", connection_state=ConnectionState.DISCONNECTED))
    store.add_player(room, _player("ok"))
    # Insertion order is preserved (host first), spectator/disconnected dropped.
    assert eligible_player_ids(room) == ["h", "ok"]


def test_cpu_counts_even_without_a_connection() -> None:
    store, room = _store_with_host()
    store.add_player(
        room, _player("cpu1", token=None, is_cpu=True, cpu_strategy=CpuStrategy.RANDOM)
    )
    assert "cpu1" in eligible_player_ids(room)


def test_min_players_and_can_start_gate() -> None:
    store, room = _store_with_host()  # host only -> |S| == 1
    assert min_players_for(RuleType.NORMAL) == 2
    assert can_start(room) is False
    store.add_player(room, _player("p2"))
    assert can_start(room) is True
