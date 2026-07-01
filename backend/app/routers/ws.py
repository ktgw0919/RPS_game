"""WebSocket game-loop endpoint (ARCHITECTURE.md §3/§4).

Scope so far (Phase 2 Steps 1/5/6):

- Connection lifecycle, room-scoped broadcast, and the JOIN-based auth flow:
  token in the first `JOIN` (never via `?token=`); non-JOIN/unknown token closes
  with `INVALID_TOKEN`; reconnect re-binds and replies `STATE_SYNC`; a live
  duplicate connection is replaced (last-wins) with `SESSION_REPLACED`.
- Envelope I/O + heartbeat (Step 5): `PING` -> `PONG`; oversized messages are
  dropped; malformed/unknown/`v`-mismatch messages get `INVALID_PAYLOAD` while
  the connection stays open (§4 message validation).
- Host settings + start (Step 6): `UPDATE_SETTINGS` -> `SETTINGS_UPDATE`,
  `START_GAME` validates the start condition (§4.2) and creates the match.
- Round loop (Steps 7-9): `SUBMIT_HAND` / `NEXT_ROUND` are thin relays to the
  `RoundRunner` (core), which owns ROUND_START/SUBMISSION_UPDATE/ROUND_RESULT/
  MATCH_END, the deadline timer, and judge-once serialization (§7/§7.1/§8).
- Lifecycle ops (Step 10): `LEAVE` (immediate in WAITING/MATCH_END with host
  hand-off + PLAYER_LEFT/HOST_CHANGED, disconnect-equivalent mid-match) and
  `RETURN_TO_LOBBY` (host-only; merge spectators, prune ghosts). Background
  TTL/transfer/ghost sweeping lives in `core/lifecycle.py` (§6/§10).

Room-state writes are serialized under the per-room lock; actual WS sends happen
outside the lock (§4/§7.1), mirroring `_attach`/`_detach`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.config import Settings
from app.core.connection_manager import ConnectionManager
from app.core.constants import ROOM_CAPACITY, WS_MAX_MESSAGE_BYTES, WS_PROTOCOL_VERSION
from app.core.round_runner import RoundRunner
from app.core.security import generate_player_id
from app.core.state_store import GameStateStore
from app.game.cpu import last_cpu_player_id, next_cpu_display_name
from app.game.start_conditions import can_start, eligible_player_ids, min_players_for
from app.models import (
    AddCpuPayload,
    ConnectionState,
    CpuStrategy,
    ErrorCode,
    ErrorPayload,
    HostChangedPayload,
    InboundEnvelope,
    JoinPayload,
    LeavePayload,
    LobbyUpdatePayload,
    MatchConfig,
    MatchState,
    MatchView,
    MessageType,
    NextRoundPayload,
    Player,
    PlayerJoinedPayload,
    PlayerLeftPayload,
    RemoveCpuPayload,
    ReturnToLobbyPayload,
    Room,
    RoomStatus,
    RuleType,
    SettingsUpdatePayload,
    StartGamePayload,
    StateSyncPayload,
    SubmitHandPayload,
    TournamentPair,
    UpdateCpuPayload,
    UpdateSettingsPayload,
    make_envelope,
)
from app.utils import generate_match_id, isoformat_utc, utcnow

logger = logging.getLogger("rps.ws")

router = APIRouter(tags=["ws"])


# --------------------------------------------------------------------------
# Envelope helpers
# --------------------------------------------------------------------------
def _envelope(message_type: MessageType, payload: dict[str, Any]) -> dict[str, Any]:
    return make_envelope(message_type, payload)


def _error_envelope(code: ErrorCode, message: str) -> dict[str, Any]:
    payload = ErrorPayload(code=code, message=message).model_dump(mode="json")
    return _envelope(MessageType.ERROR, payload)


def _parse_envelope(raw: str) -> InboundEnvelope | None:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return InboundEnvelope.model_validate(data)
    except ValidationError:
        return None


def _match_view(room: Room, viewer_id: str) -> MatchView | None:
    if room.match is None:
        return None
    match = room.match
    deadline_at = None
    my_submitted = False
    segment_id: str | None = None
    if match.rule_type is RuleType.TOURNAMENT:
        pair = _pair_for_player(match.tournament_active_pairs, viewer_id)
        if pair is not None and len(pair.players) > 1:
            segment_id = pair.segment_id
            rnd = match.tournament_segment_rounds.get(segment_id)
            if rnd is not None:
                deadline_at = rnd.deadline_at
                my_submitted = viewer_id in rnd.submissions
    elif match.current_round is not None:
        deadline_at = match.current_round.deadline_at
        my_submitted = viewer_id in match.current_round.submissions
    return MatchView(
        match_id=match.match_id,
        rule_type=match.rule_type,
        state=match.state,
        current_round_no=match.current_round_no,
        alive_player_ids=match.alive_player_ids,
        scores=match.scores,
        deadline_at=deadline_at,
        my_submitted=my_submitted,
        boss_player_id=match.boss_player_id,
        segment_id=segment_id,
        switched_to_normal_finish=(
            match.switched_to_normal_finish if match.rule_type is RuleType.MINORITY else False
        ),
    )


def _state_sync(room: Room, you: Player) -> dict[str, Any]:
    payload = StateSyncPayload(
        room=room.to_view(),
        members=[p.to_view() for p in room.members.values()],
        you=you.to_view(),
        match=_match_view(room, you.player_id),
        server_now=isoformat_utc(utcnow()),
    )
    return _envelope(MessageType.STATE_SYNC, payload.model_dump(mode="json"))


def _lobby_update(room: Room) -> dict[str, Any]:
    payload = LobbyUpdatePayload(
        members=[p.to_view() for p in room.members.values()],
        host_player_id=room.host_player_id,
        config=room.config,
    )
    return _envelope(MessageType.LOBBY_UPDATE, payload.model_dump(mode="json"))


def _settings_update(room: Room) -> dict[str, Any]:
    payload = SettingsUpdatePayload(config=room.config)
    return _envelope(MessageType.SETTINGS_UPDATE, payload.model_dump(mode="json"))


def _start_condition_message(room: Room) -> str:
    """Human-readable START_GAME rejection (§4.2)."""
    if room.config.rule_type is RuleType.BOSS:
        if not room.config.boss_player_id:
            return "Select a boss before starting."
        eligible = set(eligible_player_ids(room))
        if room.config.boss_player_id not in eligible:
            return "The nominated boss is not available."
    if len(eligible_player_ids(room)) < min_players_for(room.config.rule_type):
        return "Not enough players to start."
    return "Start conditions are not met."


def _pair_for_player(pairs: list[TournamentPair], player_id: str) -> TournamentPair | None:
    for pair in pairs:
        if player_id in pair.players:
            return pair
    return None


def _validate_submit_segment(
    room: Room, player_id: str, segment_id: str | None
) -> ErrorCode | None:
    """Validate SUBMIT_HAND segment_id for the active rule (§4 / TODO R1)."""
    match = room.match
    if match is None or room.status is not RoomStatus.IN_GAME:
        return ErrorCode.INVALID_STATE
    if match.rule_type is RuleType.TOURNAMENT:
        if segment_id is None:
            return ErrorCode.INVALID_STATE
        pair = _pair_for_player(match.tournament_active_pairs, player_id)
        if pair is None or pair.segment_id != segment_id:
            return ErrorCode.INVALID_STATE
    elif segment_id is not None:
        return ErrorCode.INVALID_STATE
    return None


def _clear_boss_nomination_if_needed(
    store: GameStateStore, room: Room, departed_player_id: str
) -> dict[str, Any] | None:
    """Reset boss_player_id when the nominee leaves the lobby (§8)."""
    if room.config.rule_type is not RuleType.BOSS:
        return None
    if room.config.boss_player_id != departed_player_id:
        return None
    store.set_config(room, room.config.model_copy(update={"boss_player_id": None}))
    return _settings_update(room)


def _player_joined(player: Player) -> dict[str, Any]:
    payload = PlayerJoinedPayload(player=player.to_view())
    return _envelope(MessageType.PLAYER_JOINED, payload.model_dump(mode="json"))


def _player_left(player_id: str) -> dict[str, Any]:
    payload = PlayerLeftPayload(player_id=player_id)
    return _envelope(MessageType.PLAYER_LEFT, payload.model_dump(mode="json"))


def _host_changed(host_player_id: str) -> dict[str, Any]:
    payload = HostChangedPayload(host_player_id=host_player_id)
    return _envelope(MessageType.HOST_CHANGED, payload.model_dump(mode="json"))


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------
@router.websocket("/ws/rooms/{room_code}")
async def ws_room(websocket: WebSocket, room_code: str) -> None:
    store: GameStateStore = websocket.app.state.store
    manager: ConnectionManager = websocket.app.state.connection_manager

    await websocket.accept()

    room = store.get_room(room_code)
    if room is None:
        await websocket.send_json(_error_envelope(ErrorCode.ROOM_NOT_FOUND, "Room not found."))
        await websocket.close()
        return
    if room.status is RoomStatus.CLOSED:
        await websocket.send_json(_error_envelope(ErrorCode.ROOM_CLOSED, "Room has been closed."))
        await websocket.close()
        return

    # First message must be a valid JOIN presenting a known token (§3).
    player = await _authenticate(websocket, store, room)
    if player is None:
        return

    await _attach(websocket, manager, store, room, player)

    try:
        await _receive_loop(websocket, manager, store, room, player)
    except WebSocketDisconnect:
        pass
    finally:
        await _detach(websocket, manager, store, room, player)


async def _authenticate(websocket: WebSocket, store: GameStateStore, room: Room) -> Player | None:
    """Read the first message; require a JOIN with a known token, else close."""
    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return None

    env = _parse_envelope(raw)
    if env is None or env.type != MessageType.JOIN:
        await websocket.send_json(
            _error_envelope(ErrorCode.INVALID_TOKEN, "First message must be JOIN with a token.")
        )
        await websocket.close()
        return None

    try:
        join = JoinPayload.model_validate(env.payload)
    except ValidationError:
        await websocket.send_json(
            _error_envelope(ErrorCode.INVALID_TOKEN, "Missing or invalid token.")
        )
        await websocket.close()
        return None

    player = store.get_player_by_token(room, join.token)
    if player is None:
        await websocket.send_json(_error_envelope(ErrorCode.INVALID_TOKEN, "Unknown token."))
        await websocket.close()
        return None
    return player


async def _attach(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
) -> None:
    """Re-bind the player to this socket, apply last-wins, and send STATE_SYNC."""
    lock = store.room_lock(room.room_code)
    async with lock:
        store.set_connection_state(room, player.player_id, ConnectionState.CONNECTED, now=utcnow())
        # PLAYER_JOINED is a one-shot UX notice; reconnects only get LOBBY_UPDATE (§4).
        announce = not player.joined_announced
        player.joined_announced = True
        state_sync = _state_sync(room, player)
        lobby_update = _lobby_update(room)
        player_joined = _player_joined(player) if announce else None

    previous = manager.register(room.room_code, player.player_id, websocket)
    if previous is not None and previous is not websocket:
        # Last-wins: a still-live duplicate connection is replaced (§3).
        await manager.send(
            previous,
            _error_envelope(ErrorCode.SESSION_REPLACED, "Replaced by a new connection."),
        )
        try:
            await previous.close()
        except Exception:
            logger.debug("Failed closing replaced socket; ignoring.", exc_info=True)

    await manager.send(websocket, state_sync)
    # Connection-state change -> authoritative roster broadcast (§4).
    await manager.broadcast(room.room_code, lobby_update)
    if player_joined is not None:
        await manager.broadcast(room.room_code, player_joined, exclude_player_id=player.player_id)


async def _receive_loop(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
) -> None:
    """Read inbound frames, validate the envelope, and dispatch by type (§4).

    Per §4 message validation, oversized frames are dropped and malformed /
    unknown / `v`-mismatch messages get `INVALID_PAYLOAD` without closing the
    socket. Disconnects propagate as `WebSocketDisconnect` to the caller.
    """
    while True:
        raw = await websocket.receive_text()
        if len(raw.encode("utf-8")) > WS_MAX_MESSAGE_BYTES:
            # Oversized inbound payload is dropped to protect the connection (§11).
            logger.debug("Dropping oversized WS message (%d bytes).", len(raw))
            continue
        env = _parse_envelope(raw)
        if env is None:
            await manager.send(
                websocket,
                _error_envelope(ErrorCode.INVALID_PAYLOAD, "Malformed message envelope."),
            )
            continue
        if env.v != WS_PROTOCOL_VERSION:
            await manager.send(
                websocket,
                _error_envelope(
                    ErrorCode.INVALID_PAYLOAD,
                    f"Unsupported protocol version; this server supports v={WS_PROTOCOL_VERSION}.",
                ),
            )
            continue
        # Any inbound frame refreshes liveness for heartbeat-miss detection (§10).
        lock = store.room_lock(room.room_code)
        async with lock:
            store.touch_player(room, player.player_id, now=utcnow())
        keep_open = await _dispatch(websocket, manager, store, room, player, env)
        if not keep_open:
            # A successful LEAVE ends the loop; the framework closes the socket on
            # return and `_detach` is a no-op (the socket was already detached).
            break


async def _dispatch(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> bool:
    """Route one validated envelope to its handler (ARCHITECTURE.md §4).

    Returns whether the connection should stay open; only a completed `LEAVE`
    returns False so the receive loop can stop reading from a detached socket.
    """
    if env.type == MessageType.PING:
        await manager.send(websocket, _envelope(MessageType.PONG, {}))
    elif env.type == MessageType.JOIN:
        lock = store.room_lock(room.room_code)
        async with lock:
            state_sync = _state_sync(room, player)
        await manager.send(websocket, state_sync)
    elif env.type == MessageType.UPDATE_SETTINGS:
        await _handle_update_settings(websocket, manager, store, room, player, env)
    elif env.type == MessageType.ADD_CPU:
        await _handle_add_cpu(websocket, manager, store, room, player, env)
    elif env.type == MessageType.REMOVE_CPU:
        await _handle_remove_cpu(websocket, manager, store, room, player, env)
    elif env.type == MessageType.UPDATE_CPU:
        await _handle_update_cpu(websocket, manager, store, room, player, env)
    elif env.type == MessageType.START_GAME:
        await _handle_start_game(websocket, manager, store, room, player, env)
    elif env.type == MessageType.SUBMIT_HAND:
        await _handle_submit_hand(websocket, manager, room, player, env)
    elif env.type == MessageType.NEXT_ROUND:
        await _handle_next_round(websocket, manager, room, player, env)
    elif env.type == MessageType.RETURN_TO_LOBBY:
        await _handle_return_to_lobby(websocket, manager, store, room, player, env)
    elif env.type == MessageType.LEAVE:
        return await _handle_leave(websocket, manager, store, room, player, env)
    else:
        await manager.send(
            websocket,
            _error_envelope(ErrorCode.INVALID_PAYLOAD, f"Unsupported message type: {env.type}."),
        )
    return True


async def _handle_update_settings(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Apply a host's partial config change and broadcast SETTINGS_UPDATE (§4/§9)."""
    if player.player_id != room.host_player_id:
        await manager.send(
            websocket, _error_envelope(ErrorCode.NOT_HOST, "Only the host can change settings.")
        )
        return
    try:
        payload = UpdateSettingsPayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid settings payload.")
        )
        return

    lock = store.room_lock(room.room_code)
    error: tuple[ErrorCode, str] | None = None
    settings_update: dict[str, Any] | None = None
    async with lock:
        if room.status is not RoomStatus.WAITING:
            error = (ErrorCode.INVALID_STATE, "Settings can only change in the lobby.")
        else:
            # Merge the diff onto the current config and re-validate the whole
            # config so §9 ranges/step rules apply (model_copy would skip them).
            merged = room.config.model_dump()
            merged.update(payload.config.model_dump(exclude_unset=True))
            try:
                new_config = MatchConfig.model_validate(merged)
            except ValidationError:
                error = (ErrorCode.INVALID_PAYLOAD, "Settings out of the allowed range.")
            else:
                store.set_config(room, new_config)
                settings_update = _settings_update(room)

    if error is not None:
        await manager.send(websocket, _error_envelope(error[0], error[1]))
        return
    assert settings_update is not None
    await manager.broadcast(room.room_code, settings_update)


async def _handle_add_cpu(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Add demo CPU players in the lobby (§4/§6). Connection stays open on error."""
    settings: Settings = websocket.app.state.settings
    if not settings.allow_cpu:
        await manager.send(
            websocket,
            _error_envelope(ErrorCode.CPU_NOT_ALLOWED, "CPU players are disabled."),
        )
        return
    if player.player_id != room.host_player_id:
        await manager.send(
            websocket, _error_envelope(ErrorCode.NOT_HOST, "Only the host can add CPUs.")
        )
        return
    try:
        payload = AddCpuPayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid ADD_CPU payload.")
        )
        return

    lock = store.room_lock(room.room_code)
    error: tuple[ErrorCode, str] | None = None
    added: list[Player] = []
    lobby_update: dict[str, Any] | None = None
    async with lock:
        if room.status is not RoomStatus.WAITING:
            error = (ErrorCode.INVALID_STATE, "CPU players can only be added in the lobby.")
        elif room.member_count() + payload.count > ROOM_CAPACITY:
            error = (ErrorCode.ROOM_FULL, "Room is full.")
        else:
            now = utcnow()
            for _ in range(payload.count):
                fixed_hands = list(payload.fixed_hands or [])
                cpu = Player(
                    player_id=generate_player_id(),
                    token=None,
                    display_name=next_cpu_display_name(room.members),
                    connection_state=ConnectionState.CONNECTED,
                    is_cpu=True,
                    cpu_strategy=payload.strategy,
                    cpu_fixed_hands=fixed_hands,
                    cpu_fixed_hand_index=0,
                    joined_at=now,
                    joined_announced=True,
                )
                store.add_player(room, cpu)
                added.append(cpu)
            lobby_update = _lobby_update(room)

    if error is not None:
        await manager.send(websocket, _error_envelope(error[0], error[1]))
        return
    assert lobby_update is not None
    for cpu in added:
        await manager.broadcast(room.room_code, _player_joined(cpu))
    await manager.broadcast(room.room_code, lobby_update)


async def _handle_update_cpu(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Set scripted hands for a lobby CPU (dev/debug). Connection stays open on error."""
    settings: Settings = websocket.app.state.settings
    if not settings.allow_cpu:
        await manager.send(
            websocket,
            _error_envelope(ErrorCode.CPU_NOT_ALLOWED, "CPU players are disabled."),
        )
        return
    if player.player_id != room.host_player_id:
        await manager.send(
            websocket, _error_envelope(ErrorCode.NOT_HOST, "Only the host can update CPUs.")
        )
        return
    try:
        payload = UpdateCpuPayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid UPDATE_CPU payload.")
        )
        return

    lock = store.room_lock(room.room_code)
    error: tuple[ErrorCode, str] | None = None
    lobby_update: dict[str, Any] | None = None
    async with lock:
        if room.status is not RoomStatus.WAITING:
            error = (ErrorCode.INVALID_STATE, "CPU players can only be updated in the lobby.")
        else:
            target = store.get_player(room, payload.player_id)
            if target is None or not target.is_cpu:
                error = (ErrorCode.INVALID_STATE, "Player is not a CPU.")
            else:
                target.cpu_strategy = CpuStrategy.FIXED
                target.cpu_fixed_hands = list(payload.fixed_hands)
                target.cpu_fixed_hand_index = 0
                store.touch(room)
                lobby_update = _lobby_update(room)

    if error is not None:
        await manager.send(websocket, _error_envelope(error[0], error[1]))
        return
    assert lobby_update is not None
    await manager.broadcast(room.room_code, lobby_update)


async def _handle_remove_cpu(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Remove a CPU from the lobby (§4). Connection stays open on error."""
    if player.player_id != room.host_player_id:
        await manager.send(
            websocket, _error_envelope(ErrorCode.NOT_HOST, "Only the host can remove CPUs.")
        )
        return
    try:
        payload = RemoveCpuPayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid REMOVE_CPU payload.")
        )
        return

    lock = store.room_lock(room.room_code)
    error: tuple[ErrorCode, str] | None = None
    removed_id: str | None = None
    lobby_update: dict[str, Any] | None = None
    async with lock:
        if room.status is not RoomStatus.WAITING:
            error = (ErrorCode.INVALID_STATE, "CPU players can only be removed in the lobby.")
        else:
            target_id = payload.player_id
            if target_id is None:
                target_id = last_cpu_player_id(room.members)
            if target_id is None:
                error = (ErrorCode.INVALID_STATE, "No CPU player to remove.")
            else:
                target = store.get_player(room, target_id)
                if target is None or not target.is_cpu:
                    error = (ErrorCode.INVALID_STATE, "Player is not a CPU.")
                else:
                    store.remove_player(room, target_id)
                    removed_id = target_id
                    lobby_update = _lobby_update(room)

    if error is not None:
        await manager.send(websocket, _error_envelope(error[0], error[1]))
        return
    assert removed_id is not None and lobby_update is not None
    await manager.broadcast(room.room_code, _player_left(removed_id))
    await manager.broadcast(room.room_code, lobby_update)


async def _handle_start_game(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Validate the start condition (§4.2) and create the match (§6)."""
    if player.player_id != room.host_player_id:
        await manager.send(
            websocket, _error_envelope(ErrorCode.NOT_HOST, "Only the host can start the game.")
        )
        return
    try:
        StartGamePayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid START_GAME payload.")
        )
        return

    lock = store.room_lock(room.room_code)
    error: tuple[ErrorCode, str] | None = None
    lobby_update: dict[str, Any] | None = None
    async with lock:
        if room.status is not RoomStatus.WAITING:
            error = (ErrorCode.INVALID_STATE, "The game has already started.")
        else:
            # Re-validate set S and rule-specific gates under the lock (§4.2).
            if not can_start(room):
                error = (ErrorCode.START_CONDITION_UNMET, _start_condition_message(room))
            else:
                store.start_match(
                    room,
                    alive_player_ids=eligible_player_ids(room),
                    config=room.config,
                    match_id=generate_match_id(),
                    now=utcnow(),
                )
                for member in room.members.values():
                    if member.is_cpu:
                        member.cpu_fixed_hand_index = 0
                lobby_update = _lobby_update(room)

    if error is not None:
        await manager.send(websocket, _error_envelope(error[0], error[1]))
        return
    assert lobby_update is not None
    await manager.broadcast(room.room_code, lobby_update)
    # Hand off to the round runner: emit the first ROUND_START + start the timer.
    runner: RoundRunner = websocket.app.state.round_runner
    await runner.start_first_round(room)


_SUBMIT_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_STATE: "Not accepting submissions right now.",
    ErrorCode.NOT_ALIVE: "Only alive players can submit a hand.",
}
_NEXT_ROUND_ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.NOT_HOST: "Only the host can advance the round.",
    ErrorCode.INVALID_STATE: "Cannot advance the round right now.",
}


async def _handle_submit_hand(
    websocket: WebSocket,
    manager: ConnectionManager,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Relay a hand to the round runner; broadcasts happen there (§4/§7)."""
    runner: RoundRunner = websocket.app.state.round_runner
    try:
        payload = SubmitHandPayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid SUBMIT_HAND payload.")
        )
        return
    segment_err = _validate_submit_segment(room, player.player_id, payload.segment_id)
    if segment_err is not None:
        await manager.send(
            websocket,
            _error_envelope(segment_err, _SUBMIT_ERROR_MESSAGES.get(segment_err, "Rejected.")),
        )
        return
    error = await runner.submit_hand(
        room, player, payload.round_no, payload.hand, segment_id=payload.segment_id
    )
    if error is not None:
        await manager.send(
            websocket, _error_envelope(error, _SUBMIT_ERROR_MESSAGES.get(error, "Rejected."))
        )


async def _handle_next_round(
    websocket: WebSocket,
    manager: ConnectionManager,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Host-only MANUAL advance to the next round (§6)."""
    runner: RoundRunner = websocket.app.state.round_runner
    try:
        NextRoundPayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid NEXT_ROUND payload.")
        )
        return
    error = await runner.next_round(room, player)
    if error is not None:
        await manager.send(
            websocket, _error_envelope(error, _NEXT_ROUND_ERROR_MESSAGES.get(error, "Rejected."))
        )


async def _handle_return_to_lobby(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> None:
    """Host returns the room to the lobby after MATCH_END (§6).

    Merges spectators into players, drops un-returned ghosts (PLAYER_LEFT), and
    broadcasts the authoritative LOBBY_UPDATE.
    """
    try:
        ReturnToLobbyPayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket,
            _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid RETURN_TO_LOBBY payload."),
        )
        return

    lock = store.room_lock(room.room_code)
    error: tuple[ErrorCode, str] | None = None
    removed: list[str] = []
    lobby_update: dict[str, Any] | None = None
    async with lock:
        if player.player_id != room.host_player_id:
            error = (ErrorCode.NOT_HOST, "Only the host can return to the lobby.")
        elif (
            room.status is not RoomStatus.IN_GAME
            or room.match is None
            or room.match.state is not MatchState.MATCH_END
        ):
            error = (ErrorCode.INVALID_STATE, "Can only return to lobby after the match ends.")
        else:
            match = room.match
            defer_normal = match is not None and match.minority_defer_normal_next_match
            removed = store.return_to_lobby(room)
            if defer_normal:
                store.set_config(
                    room, room.config.model_copy(update={"rule_type": RuleType.NORMAL})
                )
            lobby_update = _lobby_update(room)

    if error is not None:
        await manager.send(websocket, _error_envelope(error[0], error[1]))
        return
    for player_id in removed:
        await manager.broadcast(room.room_code, _player_left(player_id))
    assert lobby_update is not None
    await manager.broadcast(room.room_code, lobby_update)


async def _handle_leave(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
    env: InboundEnvelope,
) -> bool:
    """Voluntary leave (§6/§7). Returns False so the receive loop stops.

    WAITING / MATCH_END: leave immediately (PLAYER_LEFT + LOBBY_UPDATE; a WAITING
    host hands off immediately via HOST_CHANGED; human-zero closes the room).
    During an active match (COLLECTING/JUDGING/ROUND_RESULT): treated as a
    disconnect, keeping the player alive until the match ends (LOBBY_UPDATE).
    """
    try:
        LeavePayload.model_validate(env.payload)
    except ValidationError:
        await manager.send(
            websocket, _error_envelope(ErrorCode.INVALID_PAYLOAD, "Invalid LEAVE payload.")
        )
        return True

    lock = store.room_lock(room.room_code)
    close_room = False
    host_changed_id: str | None = None
    lobby_update: dict[str, Any] | None = None
    settings_update: dict[str, Any] | None = None
    removed_self = False
    async with lock:
        match = room.match
        active_match = (
            room.status is RoomStatus.IN_GAME
            and match is not None
            and match.state is not MatchState.MATCH_END
        )
        if active_match:
            # Disconnect-equivalent: keep alive for the rest of the match (§7).
            store.set_connection_state(
                room, player.player_id, ConnectionState.DISCONNECTED, now=utcnow()
            )
            lobby_update = _lobby_update(room)
        else:
            removed_self = True
            was_host = player.player_id == room.host_player_id
            store.remove_player(room, player.player_id)
            if was_host:
                new_host = store.oldest_connected_human_id(room)
                if new_host is not None:
                    store.set_host(room, new_host)
                    host_changed_id = new_host
            if not any(not p.is_cpu for p in room.members.values()):
                store.close_room(room)
                close_room = True
            else:
                settings_update = _clear_boss_nomination_if_needed(store, room, player.player_id)
                lobby_update = _lobby_update(room)

    # Detach this socket up front so the finally-`_detach` is a no-op for us.
    manager.disconnect_socket(room.room_code, player.player_id)

    if close_room:
        await manager.broadcast(
            room.room_code,
            _error_envelope(ErrorCode.ROOM_CLOSED, "Room closed."),
        )
        await manager.close_room(room.room_code)
    else:
        if removed_self:
            await manager.broadcast(room.room_code, _player_left(player.player_id))
        if host_changed_id is not None:
            await manager.broadcast(room.room_code, _host_changed(host_changed_id))
        if settings_update is not None:
            await manager.broadcast(room.room_code, settings_update)
        if lobby_update is not None:
            await manager.broadcast(room.room_code, lobby_update)

    return False


async def _detach(
    websocket: WebSocket,
    manager: ConnectionManager,
    store: GameStateStore,
    room: Room,
    player: Player,
) -> None:
    """On disconnect, mark DISCONNECTED only if this was the active socket (§7)."""
    was_active = manager.unregister(room.room_code, player.player_id, websocket)
    if not was_active:
        # This socket had already been replaced (last-wins); leave state intact.
        return
    lock = store.room_lock(room.room_code)
    async with lock:
        store.set_connection_state(
            room, player.player_id, ConnectionState.DISCONNECTED, now=utcnow()
        )
        lobby_update = _lobby_update(room)
    await manager.broadcast(room.room_code, lobby_update)
