"""REST endpoints for room creation and join (ARCHITECTURE.md §3.1/§3.2).

Tokens are returned only in the response body and presented later in the first
WS `JOIN` message. The new player's spectator flag depends on room status: a
join while IN_GAME enters as a spectator (ARCHITECTURE.md §6).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import generate_player_id, generate_player_token
from app.core.state_store import GameStateStore
from app.errors import AppError
from app.models import (
    ConnectionState,
    CreateRoomResponse,
    ErrorCode,
    JoinRequest,
    JoinRoomResponse,
    Player,
    Room,
    RoomStateResponse,
    RoomStatus,
)
from app.utils import utcnow

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _store(request: Request) -> GameStateStore:
    store: GameStateStore = request.app.state.store
    return store


def _client_ip(request: Request) -> str:
    # Behind a reverse proxy, trust the first X-Forwarded-For hop (§3.1).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_open_room(store: GameStateStore, code: str) -> Room:
    room = store.get_room(code)
    if room is None:
        raise AppError(ErrorCode.ROOM_NOT_FOUND, "Room not found.")
    if room.status is RoomStatus.CLOSED:
        raise AppError(ErrorCode.ROOM_CLOSED, "Room has been closed.")
    return room


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateRoomResponse,
)
async def create_room(body: JoinRequest, request: Request) -> CreateRoomResponse:
    limiter: SlidingWindowRateLimiter = request.app.state.room_create_limiter
    if not limiter.allow(_client_ip(request)):
        raise AppError(
            ErrorCode.INVALID_STATE,
            "Too many rooms created from this address. Try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    store = _store(request)
    token = generate_player_token()
    host = Player(
        player_id=generate_player_id(),
        token=token,
        display_name=body.display_name,
        connection_state=ConnectionState.CONNECTED,
        is_host=True,
        joined_at=utcnow(),
    )
    room = store.create_room(host)
    return CreateRoomResponse(
        room_code=room.room_code,
        player_id=host.player_id,
        player_token=token,
        room=room.to_view(),
    )


@router.post(
    "/{code}/players",
    status_code=status.HTTP_201_CREATED,
    response_model=JoinRoomResponse,
)
async def join_room(code: str, body: JoinRequest, request: Request) -> JoinRoomResponse:
    store = _store(request)
    lock = store.room_lock(code)
    async with lock:
        room = _get_open_room(store, code)
        if room.is_full():
            raise AppError(ErrorCode.ROOM_FULL, "Room is full.")

        token = generate_player_token()
        # Joining mid-game enters as a spectator until the next match (§6).
        is_spectator = room.status is RoomStatus.IN_GAME
        player = Player(
            player_id=generate_player_id(),
            token=token,
            display_name=body.display_name,
            connection_state=ConnectionState.CONNECTED,
            is_spectator=is_spectator,
            joined_at=utcnow(),
        )
        store.add_player(room, player)
        return JoinRoomResponse(
            player_id=player.player_id,
            player_token=token,
            room=room.to_view(),
        )


@router.get("/{code}", response_model=RoomStateResponse)
async def get_room(code: str, request: Request) -> RoomStateResponse:
    store = _store(request)
    room = _get_open_room(store, code)
    return RoomStateResponse(room=room.to_view())
