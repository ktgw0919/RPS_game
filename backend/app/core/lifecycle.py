"""Background room lifecycle sweep (ARCHITECTURE.md §10).

A single resident task started from `lifespan` runs `sweep_once` every
`ROOM_SWEEP_INTERVAL_SEC` and applies, per room:

1. Idle teardown: no activity for `room_idle_ttl_sec` -> CLOSED (+ ERROR
   ROOM_CLOSED to connected clients, then their sockets are closed).
2. Heartbeat miss: a CONNECTED human silent for > HEARTBEAT_TIMEOUT_SEC is
   marked DISCONNECTED.
3. Host auto-transfer: a missing/DISCONNECTED host past `host_transfer_grace_sec`
   hands off to the oldest CONNECTED human (CPU excluded) -> HOST_CHANGED.
4. Ghost removal (WAITING only): a DISCONNECTED human past `ghost_ttl_sec` is
   dropped -> PLAYER_LEFT. IN_GAME keeps DISCONNECTED players alive (§7).
5. Human-zero: a room with no human members left is CLOSED immediately.

State writes run under the per-room lock; actual WS sends happen outside it
(§4/§7.1). `now`/`sleep` are injected so the sweep is deterministically testable
(.cursor/rules/backend.mdc): unit tests call `sweep_once(now)` directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.config import Settings
from app.core.connection_manager import ConnectionManager
from app.core.constants import HEARTBEAT_TIMEOUT_SEC, ROOM_SWEEP_INTERVAL_SEC
from app.core.state_store import GameStateStore
from app.models import (
    ConnectionState,
    ErrorCode,
    ErrorPayload,
    HostChangedPayload,
    LobbyUpdatePayload,
    MessageType,
    PlayerLeftPayload,
    Room,
    RoomStatus,
    make_envelope,
)
from app.utils import utcnow

logger = logging.getLogger("rps.lifecycle")

NowFn = Callable[[], datetime]
SleepFn = Callable[[float], Awaitable[None]]


async def _real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


@dataclass
class _RoomActions:
    """What a single room's locked sweep decided; applied as I/O afterwards."""

    close: bool = False
    lobby_update: dict[str, Any] | None = None
    host_changed: dict[str, Any] | None = None
    player_left: list[dict[str, Any]] = field(default_factory=list)


class LifecycleManager:
    """Resident sweep enforcing room TTLs, host transfer, and ghost removal (§10)."""

    def __init__(
        self,
        store: GameStateStore,
        manager: ConnectionManager,
        settings: Settings,
        *,
        now: NowFn = utcnow,
        sleep: SleepFn = _real_sleep,
        interval_sec: float = ROOM_SWEEP_INTERVAL_SEC,
    ) -> None:
        self._store = store
        self._manager = manager
        self._settings = settings
        self._now = now
        self._sleep = sleep
        self._interval = interval_sec
        self._task: asyncio.Task[None] | None = None

    # --------------------------------------------------------------- lifespan
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(BaseException):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._sleep(self._interval)
            except asyncio.CancelledError:
                return
            try:
                await self.sweep_once(self._now())
            except Exception:
                logger.exception("Room lifecycle sweep failed; continuing.")

    # ------------------------------------------------------------------ sweep
    async def sweep_once(self, now: datetime) -> None:
        for room in self._store.all_rooms():
            if room.status is RoomStatus.CLOSED:
                continue
            actions = await self._evaluate_room(room, now)
            await self._apply(room, actions)

    async def _evaluate_room(self, room: Room, now: datetime) -> _RoomActions:
        actions = _RoomActions()
        lock = self._store.room_lock(room.room_code)
        async with lock:
            if room.status is RoomStatus.CLOSED:
                return actions

            # 1. Idle teardown supersedes everything else.
            idle_sec = (now - room.last_active_at).total_seconds()
            if idle_sec >= self._settings.room_idle_ttl_sec:
                self._store.close_room(room)
                actions.close = True
                return actions

            changed = False

            # 2. Heartbeat miss -> DISCONNECTED.
            for player in list(room.members.values()):
                if (
                    not player.is_cpu
                    and player.connection_state is ConnectionState.CONNECTED
                    and player.last_seen_at is not None
                    and (now - player.last_seen_at).total_seconds() > HEARTBEAT_TIMEOUT_SEC
                ):
                    self._store.set_connection_state(
                        room, player.player_id, ConnectionState.DISCONNECTED, now=now
                    )
                    changed = True

            # 3. Host auto-transfer (grace elapsed).
            if self._host_needs_transfer(room, now):
                new_host = self._store.oldest_connected_human_id(
                    room, exclude_id=room.host_player_id
                )
                if new_host is not None:
                    self._store.set_host(room, new_host)
                    actions.host_changed = make_envelope(
                        MessageType.HOST_CHANGED,
                        HostChangedPayload(host_player_id=new_host).model_dump(mode="json"),
                    )
                    changed = True

            # 4. Ghost removal (WAITING only).
            if room.status is RoomStatus.WAITING:
                for player in list(room.members.values()):
                    if (
                        not player.is_cpu
                        and player.connection_state is ConnectionState.DISCONNECTED
                        and player.disconnected_at is not None
                        and (now - player.disconnected_at).total_seconds()
                        > self._settings.ghost_ttl_sec
                    ):
                        self._store.remove_player(room, player.player_id)
                        actions.player_left.append(
                            make_envelope(
                                MessageType.PLAYER_LEFT,
                                PlayerLeftPayload(player_id=player.player_id).model_dump(
                                    mode="json"
                                ),
                            )
                        )
                        changed = True

            # 5. Human-zero -> close.
            if not any(not p.is_cpu for p in room.members.values()):
                self._store.close_room(room)
                actions.close = True
                actions.host_changed = None
                actions.player_left = []
                return actions

            if changed:
                actions.lobby_update = make_envelope(
                    MessageType.LOBBY_UPDATE,
                    LobbyUpdatePayload(
                        members=[p.to_view() for p in room.members.values()],
                        host_player_id=room.host_player_id,
                        config=room.config,
                    ).model_dump(mode="json"),
                )
        return actions

    def _host_needs_transfer(self, room: Room, now: datetime) -> bool:
        host = room.members.get(room.host_player_id) if room.host_player_id else None
        if host is None:
            return True  # host left/removed; promote a successor
        if host.connection_state is not ConnectionState.DISCONNECTED:
            return False
        if host.disconnected_at is None:
            return False
        elapsed = (now - host.disconnected_at).total_seconds()
        return elapsed >= self._settings.host_transfer_grace_sec

    async def _apply(self, room: Room, actions: _RoomActions) -> None:
        if actions.close:
            await self._manager.broadcast(
                room.room_code,
                make_envelope(
                    MessageType.ERROR,
                    ErrorPayload(code=ErrorCode.ROOM_CLOSED, message="Room closed.").model_dump(
                        mode="json"
                    ),
                ),
            )
            await self._manager.close_room(room.room_code)
            return
        for msg in actions.player_left:
            await self._manager.broadcast(room.room_code, msg)
        if actions.host_changed is not None:
            await self._manager.broadcast(room.room_code, actions.host_changed)
        if actions.lobby_update is not None:
            await self._manager.broadcast(room.room_code, actions.lobby_update)
