"""WebSocket connection registry (ARCHITECTURE.md §3/§4).

Tracks the live WebSocket per (room, player) and provides room-scoped
broadcast / individual send. This holds only transport connections; the
authoritative game/room/player state lives in `GameStateStore`.

Identity / reconnection rules handled here:
- One active socket per `player_id` within a room. Registering a new socket for
  a player that already has one returns the previous socket so the caller can
  apply last-wins (send `SESSION_REPLACED` and close it) (§3).
- Removal only evicts the socket that is still the registered one, so a stale
  (replaced) socket closing does not detach the new connection.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("rps.ws")


class ConnectionManager:
    def __init__(self) -> None:
        # room_code (uppercase) -> player_id -> active WebSocket
        self._rooms: dict[str, dict[str, WebSocket]] = {}

    def register(self, room_code: str, player_id: str, websocket: WebSocket) -> WebSocket | None:
        """Register `websocket` as the active socket for the player.

        Returns the previously-registered socket for this player if one existed
        (the caller applies last-wins), otherwise None.
        """
        room = self._rooms.setdefault(room_code.upper(), {})
        previous = room.get(player_id)
        room[player_id] = websocket
        return previous

    def unregister(self, room_code: str, player_id: str, websocket: WebSocket) -> bool:
        """Remove the player's socket iff it is exactly `websocket`.

        Returns True if this socket was the active one and was removed (the
        player is now without a live connection); False if it had already been
        replaced by a newer socket.
        """
        room = self._rooms.get(room_code.upper())
        if room is None:
            return False
        if room.get(player_id) is not websocket:
            return False
        del room[player_id]
        if not room:
            del self._rooms[room_code.upper()]
        return True

    def is_connected(self, room_code: str, player_id: str) -> bool:
        room = self._rooms.get(room_code.upper())
        return room is not None and player_id in room

    async def send(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        """Send one envelope to a single socket (best-effort)."""
        try:
            await websocket.send_json(message)
        except Exception:
            logger.debug("Failed to send to a websocket; ignoring.", exc_info=True)

    async def broadcast(
        self,
        room_code: str,
        message: dict[str, Any],
        *,
        exclude_player_id: str | None = None,
    ) -> None:
        """Send one envelope to every socket in the room (best-effort)."""
        room = self._rooms.get(room_code.upper())
        if not room:
            return
        for player_id, websocket in list(room.items()):
            if player_id == exclude_player_id:
                continue
            await self.send(websocket, message)

    async def close_room(self, room_code: str) -> None:
        """Close and forget every socket in the room (room teardown, §10)."""
        room = self._rooms.pop(room_code.upper(), None)
        if not room:
            return
        for websocket in list(room.values()):
            try:
                await websocket.close()
            except Exception:
                logger.debug("Failed closing socket on room teardown; ignoring.", exc_info=True)

    def disconnect_socket(self, room_code: str, player_id: str) -> WebSocket | None:
        """Forget and return a player's socket without closing it (caller closes)."""
        room = self._rooms.get(room_code.upper())
        if room is None:
            return None
        ws = room.pop(player_id, None)
        if not room:
            self._rooms.pop(room_code.upper(), None)
        return ws
