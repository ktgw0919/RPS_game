"""Lifecycle sweep unit tests (ARCHITECTURE.md §10).

The sweep is exercised directly via `sweep_once(now)` with an injected clock and
hand-set player timestamps, so idle teardown / heartbeat miss / host transfer /
ghost removal / human-zero close are all deterministic (no wall clock, no real
sockets). The ConnectionManager has no registered sockets, so broadcasts are
harmless no-ops.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import Settings
from app.core.connection_manager import ConnectionManager
from app.core.lifecycle import LifecycleManager
from app.core.state_store import InMemoryGameStateStore
from app.models import ConnectionState, Player, RoomStatus

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        db_url="mongodb://localhost:27017",
        db_name="rps_test",
        host_transfer_grace_sec=30,
        ghost_ttl_sec=120,
        room_idle_ttl_sec=1800,
    )


def _player(pid: str, *, joined: datetime = NOW, **kwargs: Any) -> Player:
    kwargs.setdefault("token", f"tok-{pid}")
    return Player(player_id=pid, display_name=pid, joined_at=joined, **kwargs)


def _setup() -> tuple[LifecycleManager, InMemoryGameStateStore, Any]:
    store = InMemoryGameStateStore()
    lifecycle = LifecycleManager(store, ConnectionManager(), _settings(), now=lambda: NOW)
    room = store.create_room(_player("h"))
    room.last_active_at = NOW  # avoid accidental idle teardown
    return lifecycle, store, room


async def test_idle_room_is_closed() -> None:
    lifecycle, _store, room = _setup()
    room.last_active_at = NOW - timedelta(seconds=1800 + 5)

    await lifecycle.sweep_once(NOW)

    assert room.status is RoomStatus.CLOSED


async def test_heartbeat_miss_marks_disconnected() -> None:
    lifecycle, store, room = _setup()
    room.members["h"].last_seen_at = NOW  # host still alive
    store.add_player(room, _player("p2", joined=NOW + timedelta(seconds=1)))
    room.members["p2"].last_seen_at = NOW - timedelta(seconds=70)  # silent > 60s
    room.last_active_at = NOW

    await lifecycle.sweep_once(NOW)

    assert room.members["p2"].connection_state is ConnectionState.DISCONNECTED
    assert room.members["p2"].disconnected_at == NOW
    assert room.members["h"].connection_state is ConnectionState.CONNECTED


async def test_host_transfer_after_grace_promotes_oldest_human() -> None:
    lifecycle, store, room = _setup()
    store.add_player(room, _player("p2", joined=NOW + timedelta(seconds=1)))
    store.add_player(room, _player("p3", joined=NOW + timedelta(seconds=2)))
    # Host disconnected past the grace window.
    room.members["h"].connection_state = ConnectionState.DISCONNECTED
    room.members["h"].disconnected_at = NOW - timedelta(seconds=40)
    room.last_active_at = NOW

    await lifecycle.sweep_once(NOW)

    assert room.host_player_id == "p2"  # oldest CONNECTED human
    assert room.members["p2"].is_host is True
    assert room.members["h"].is_host is False


async def test_host_transfer_waits_for_grace() -> None:
    lifecycle, store, room = _setup()
    store.add_player(room, _player("p2", joined=NOW + timedelta(seconds=1)))
    room.members["h"].connection_state = ConnectionState.DISCONNECTED
    room.members["h"].disconnected_at = NOW - timedelta(seconds=10)  # < 30s grace
    room.last_active_at = NOW

    await lifecycle.sweep_once(NOW)

    assert room.host_player_id == "h"  # not transferred yet


async def test_ghost_removed_in_waiting() -> None:
    lifecycle, store, room = _setup()
    store.add_player(room, _player("p2", joined=NOW + timedelta(seconds=1)))
    room.members["p2"].connection_state = ConnectionState.DISCONNECTED
    room.members["p2"].disconnected_at = NOW - timedelta(seconds=130)  # > 120s TTL
    room.last_active_at = NOW

    await lifecycle.sweep_once(NOW)

    assert "p2" not in room.members
    assert room.status is RoomStatus.WAITING


async def test_in_game_disconnect_kept_alive() -> None:
    lifecycle, store, room = _setup()
    store.add_player(room, _player("p2", joined=NOW + timedelta(seconds=1)))
    store.start_match(
        room, alive_player_ids=["h", "p2"], config=room.config, match_id="m1", now=NOW
    )
    room.members["p2"].connection_state = ConnectionState.DISCONNECTED
    room.members["p2"].disconnected_at = NOW - timedelta(seconds=130)  # would be a ghost in WAITING
    room.last_active_at = NOW

    await lifecycle.sweep_once(NOW)

    assert "p2" in room.members  # IN_GAME keeps disconnected players alive (§7)
    assert room.status is RoomStatus.IN_GAME


async def test_human_zero_closes_room() -> None:
    lifecycle, _store, room = _setup()
    # The only human is a long-gone ghost; after removal there are no humans left.
    room.members["h"].connection_state = ConnectionState.DISCONNECTED
    room.members["h"].disconnected_at = NOW - timedelta(seconds=130)
    room.last_active_at = NOW

    await lifecycle.sweep_once(NOW)

    assert room.status is RoomStatus.CLOSED
    assert "h" not in room.members
