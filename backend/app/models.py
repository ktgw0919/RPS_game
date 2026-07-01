"""Pydantic v2 schemas and domain models.

These mirror the TypeScript types in `frontend/src/types`. Any change to a WS
payload / view DTO / ErrorCode must update both sides in the same change
(see .cursor/rules/00-project.mdc and ARCHITECTURE.md §4).

Layers:
- Enums + value types (Hand, RuleType, ...)
- MatchConfig (host settings, ARCHITECTURE.md §9)
- Internal domain models (Player, Room, Match, Round)  Ehold authoritative state
- View DTOs (PlayerView, RoomView, MatchView)  Ewhat is sent to clients (no token)
- REST request/response DTOs (ARCHITECTURE.md §3.1)
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.core.constants import (
    DISPLAY_NAME_MAX_LEN,
    DISPLAY_NAME_MIN_LEN,
    ROOM_CAPACITY,
    WS_PROTOCOL_VERSION,
)
from app.utils import isoformat_utc


# --------------------------------------------------------------------------
# Enums / value types (ARCHITECTURE.md §4/§5/§6/§9)
# --------------------------------------------------------------------------
class Hand(StrEnum):
    ROCK = "ROCK"
    SCISSORS = "SCISSORS"
    PAPER = "PAPER"


class CpuStrategy(StrEnum):
    # MVP only supports RANDOM; the enum is a container for future strategies.
    RANDOM = "RANDOM"


class RuleType(StrEnum):
    NORMAL = "NORMAL"
    MINORITY = "MINORITY"
    BOSS = "BOSS"
    TOURNAMENT = "TOURNAMENT"


class NormalEndMode(StrEnum):
    ELIMINATION = "ELIMINATION"
    SINGLE_ROUND = "SINGLE_ROUND"


class RoundAdvanceMode(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class MinorityFinishTiming(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    NEXT_MATCH = "NEXT_MATCH"


class RoomStatus(StrEnum):
    WAITING = "WAITING"
    IN_GAME = "IN_GAME"
    CLOSED = "CLOSED"


class MatchState(StrEnum):
    COLLECTING = "COLLECTING"
    JUDGING = "JUDGING"
    ROUND_RESULT = "ROUND_RESULT"
    MATCH_END = "MATCH_END"


class MatchEndReason(StrEnum):
    """Why a match ended (ARCHITECTURE.md §4 MATCH_END payload)."""

    DECIDED = "DECIDED"
    DRAW_MAX_ROUNDS = "DRAW_MAX_ROUNDS"


class ConnectionState(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class ErrorCode(StrEnum):
    """Shared error codes (ARCHITECTURE.md §4.1). Kept in sync with the frontend."""

    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    ROOM_FULL = "ROOM_FULL"
    ROOM_CLOSED = "ROOM_CLOSED"
    INVALID_TOKEN = "INVALID_TOKEN"
    SESSION_REPLACED = "SESSION_REPLACED"
    DISPLAY_NAME_INVALID = "DISPLAY_NAME_INVALID"
    NOT_HOST = "NOT_HOST"
    NOT_ALIVE = "NOT_ALIVE"
    INVALID_STATE = "INVALID_STATE"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    START_CONDITION_UNMET = "START_CONDITION_UNMET"
    CPU_NOT_ALLOWED = "CPU_NOT_ALLOWED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


# --------------------------------------------------------------------------
# Display name normalization (ARCHITECTURE.md §3.2)
# --------------------------------------------------------------------------
def normalize_display_name(raw: str) -> str:
    """Trim and strip control chars; raise ValueError if out of 1..20 chars.

    Unicode (emoji / multilingual) is allowed; control characters (newline, tab,
    zero-width, etc.) are rejected. Server-side validation is authoritative.
    """
    # Drop Unicode "Other" category (Cc/Cf/Cs/Co/Cn) -> control & format chars.
    cleaned = "".join(ch for ch in raw if unicodedata.category(ch)[0] != "C")
    cleaned = cleaned.strip()
    if not (DISPLAY_NAME_MIN_LEN <= len(cleaned) <= DISPLAY_NAME_MAX_LEN):
        raise ValueError(
            f"display_name must be {DISPLAY_NAME_MIN_LEN}-{DISPLAY_NAME_MAX_LEN} chars"
        )
    return cleaned


# --------------------------------------------------------------------------
# MatchConfig (ARCHITECTURE.md §9)  Eranges/defaults are authoritative here
# --------------------------------------------------------------------------
class MatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_type: RuleType = RuleType.NORMAL
    normal_end_mode: NormalEndMode = NormalEndMode.ELIMINATION
    round_time_limit_sec: int = Field(default=10, ge=5, le=60)
    round_advance_mode: RoundAdvanceMode = RoundAdvanceMode.AUTO
    result_display_sec: int = Field(default=3, ge=1, le=10)
    max_draw_rounds: int = Field(default=5, ge=1, le=20)
    minority_finish_threshold: int = Field(default=2, ge=2)
    minority_finish_timing: MinorityFinishTiming = MinorityFinishTiming.IMMEDIATE
    boss_player_id: str | None = None

    @field_validator("round_time_limit_sec")
    @classmethod
    def _time_limit_step(cls, v: int) -> int:
        if v % 5 != 0:
            raise ValueError("round_time_limit_sec must be a multiple of 5")
        return v


class MatchConfigUpdate(BaseModel):
    """Partial update for UPDATE_SETTINGS (Phase 2). Only provided fields apply."""

    model_config = ConfigDict(extra="forbid")

    rule_type: RuleType | None = None
    normal_end_mode: NormalEndMode | None = None
    round_time_limit_sec: int | None = Field(default=None, ge=5, le=60)
    round_advance_mode: RoundAdvanceMode | None = None
    result_display_sec: int | None = Field(default=None, ge=1, le=10)
    max_draw_rounds: int | None = Field(default=None, ge=1, le=20)
    minority_finish_threshold: int | None = Field(default=None, ge=2)
    minority_finish_timing: MinorityFinishTiming | None = None
    boss_player_id: str | None = None


# --------------------------------------------------------------------------
# Internal domain models (authoritative live state; ARCHITECTURE.md §5)
# --------------------------------------------------------------------------
class Player(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    # Verification token. CPU players have no token (None).
    token: str | None = None
    display_name: str
    connection_state: ConnectionState = ConnectionState.CONNECTED
    is_host: bool = False
    is_spectator: bool = False
    is_cpu: bool = False
    cpu_strategy: CpuStrategy | None = None
    joined_at: datetime
    # Lifecycle bookkeeping (internal; never serialized to clients via PlayerView).
    # `last_seen_at`: last inbound frame, for heartbeat-miss detection (§10).
    # `disconnected_at`: when CONNECTED->DISCONNECTED, for ghost TTL / host grace (§10).
    # `joined_announced`: whether PLAYER_JOINED has fired once for this player (§4).
    last_seen_at: datetime | None = None
    disconnected_at: datetime | None = None
    joined_announced: bool = False

    def to_view(self) -> PlayerView:
        return PlayerView(
            player_id=self.player_id,
            display_name=self.display_name,
            is_host=self.is_host,
            # CPU players are always reported CONNECTED (ARCHITECTURE.md §3).
            connection_state=(ConnectionState.CONNECTED if self.is_cpu else self.connection_state),
            is_spectator=self.is_spectator,
            is_cpu=self.is_cpu,
        )


class Round(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_no: int
    deadline_at: datetime | None = None
    submissions: dict[str, Hand] = Field(default_factory=dict)
    judged_at: datetime | None = None


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    rule_type: RuleType = RuleType.NORMAL
    state: MatchState = MatchState.COLLECTING
    config: MatchConfig
    alive_player_ids: list[str] = Field(default_factory=list)
    # Snapshot of start set S at START_GAME; used for match_history (§6).
    participant_player_ids: list[str] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    current_round_no: int = 0
    # Live round being collected/judged (internal; not part of MatchView).
    current_round: Round | None = None
    # Count of draws (same-member replays) so far; gates max_draw_rounds (§9).
    draw_round_count: int = 0
    boss_player_id: str | None = None
    winner_ids: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Room(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_code: str
    host_player_id: str | None = None
    status: RoomStatus = RoomStatus.WAITING
    members: dict[str, Player] = Field(default_factory=dict)
    config: MatchConfig = Field(default_factory=MatchConfig)
    match: Match | None = None
    created_at: datetime
    last_active_at: datetime

    def member_count(self) -> int:
        """Capacity count: all human + spectator + CPU, CONNECTED or DISCONNECTED."""
        return len(self.members)

    def is_full(self) -> bool:
        return self.member_count() >= ROOM_CAPACITY

    def to_view(self) -> RoomView:
        return RoomView(
            room_code=self.room_code,
            status=self.status,
            host_player_id=self.host_player_id,
            member_count=self.member_count(),
            capacity=ROOM_CAPACITY,
            config=self.config,
        )


# --------------------------------------------------------------------------
# View DTOs (ARCHITECTURE.md §4 "ビュー垁E)  Enever include token
# --------------------------------------------------------------------------
class PlayerView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    display_name: str
    is_host: bool
    connection_state: ConnectionState
    is_spectator: bool
    is_cpu: bool


class RoomView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_code: str
    status: RoomStatus
    host_player_id: str | None
    member_count: int
    capacity: int
    config: MatchConfig


class MatchView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    rule_type: RuleType
    state: MatchState
    current_round_no: int
    alive_player_ids: list[str]
    scores: dict[str, int]
    deadline_at: datetime | None = None
    my_submitted: bool = False
    boss_player_id: str | None = None

    @field_serializer("deadline_at")
    def _ser_deadline_at(self, value: datetime | None) -> str | None:
        # UTC ISO8601, millisecond precision, trailing 'Z' (ARCHITECTURE.md §4).
        return isoformat_utc(value) if value is not None else None


# --------------------------------------------------------------------------
# REST DTOs (ARCHITECTURE.md §3.1)
# --------------------------------------------------------------------------
class JoinRequest(BaseModel):
    """Body for POST /rooms and POST /rooms/{code}/players."""

    model_config = ConfigDict(extra="forbid")

    display_name: str

    @field_validator("display_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return normalize_display_name(v)


class CreateRoomResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_code: str
    player_id: str
    player_token: str
    room: RoomView


class JoinRoomResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    player_token: str
    room: RoomView


class RoomStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room: RoomView


class MatchHistoryPlayerEntry(BaseModel):
    """Participant row in a match history entry (ARCHITECTURE.md §3.1 / §6)."""

    model_config = ConfigDict(extra="forbid")

    player_id: str
    display_name: str
    is_cpu: bool


class MatchHistoryEntry(BaseModel):
    """One finished match in `GET /rooms/{code}/matches` (ARCHITECTURE.md §3.1)."""

    model_config = ConfigDict(extra="forbid")

    match_id: str
    rule_type: RuleType
    players: list[MatchHistoryPlayerEntry]
    winner_ids: list[str] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    started_at: datetime
    ended_at: datetime

    @field_serializer("started_at", "ended_at")
    def _serialize_timestamps(self, value: datetime) -> str:
        return isoformat_utc(value)


class MatchHistoryListResponse(BaseModel):
    """`GET /rooms/{code}/matches` success body (ARCHITECTURE.md §3.1)."""

    model_config = ConfigDict(extra="forbid")

    room_code: str
    matches: list[MatchHistoryEntry]
    has_more: bool


class ErrorResponse(BaseModel):
    """REST error body: {code, message} (ARCHITECTURE.md §3.1 / §4.1)."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str


class PublicConfigResponse(BaseModel):
    """Public server flags exposed to clients (ARCHITECTURE.md §3 / §11)."""

    model_config = ConfigDict(extra="forbid")

    allow_cpu: bool


# --------------------------------------------------------------------------
# WebSocket protocol (ARCHITECTURE.md §4) — envelope {type, payload, v}
# Mirrored in frontend/src/types. Message types are added together with their
# handlers; submit/round/match-end types arrive in later steps (§4 table).
# --------------------------------------------------------------------------
class MessageType(StrEnum):
    """WS message `type` values currently implemented (ARCHITECTURE.md §4)."""

    # client -> server
    JOIN = "JOIN"
    PING = "PING"
    UPDATE_SETTINGS = "UPDATE_SETTINGS"
    START_GAME = "START_GAME"
    SUBMIT_HAND = "SUBMIT_HAND"
    NEXT_ROUND = "NEXT_ROUND"
    RETURN_TO_LOBBY = "RETURN_TO_LOBBY"
    LEAVE = "LEAVE"
    ADD_CPU = "ADD_CPU"
    REMOVE_CPU = "REMOVE_CPU"
    # server -> client
    STATE_SYNC = "STATE_SYNC"
    LOBBY_UPDATE = "LOBBY_UPDATE"
    SETTINGS_UPDATE = "SETTINGS_UPDATE"
    ROUND_START = "ROUND_START"
    SUBMISSION_UPDATE = "SUBMISSION_UPDATE"
    ROUND_RESULT = "ROUND_RESULT"
    MATCH_END = "MATCH_END"
    PLAYER_JOINED = "PLAYER_JOINED"
    PLAYER_LEFT = "PLAYER_LEFT"
    HOST_CHANGED = "HOST_CHANGED"
    PONG = "PONG"
    ERROR = "ERROR"


def make_envelope(message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a payload in the WS envelope `{type, payload, v}` (ARCHITECTURE.md §4)."""
    return {"type": str(message_type), "payload": payload, "v": WS_PROTOCOL_VERSION}


class InboundEnvelope(BaseModel):
    """Parsed envelope of an inbound WS message: {type, payload, v}."""

    model_config = ConfigDict(extra="forbid")

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    v: int = WS_PROTOCOL_VERSION


class JoinPayload(BaseModel):
    """`JOIN` payload: the REST-issued player token (ARCHITECTURE.md §3/§4)."""

    model_config = ConfigDict(extra="forbid")

    token: str


class StateSyncPayload(BaseModel):
    """`STATE_SYNC` snapshot sent to a single (re)connecting client (§4)."""

    model_config = ConfigDict(extra="forbid")

    room: RoomView
    members: list[PlayerView]
    you: PlayerView
    match: MatchView | None = None
    server_now: str


class LobbyUpdatePayload(BaseModel):
    """`LOBBY_UPDATE` authoritative roster/host snapshot broadcast (§4)."""

    model_config = ConfigDict(extra="forbid")

    members: list[PlayerView]
    host_player_id: str | None
    config: MatchConfig


class ErrorPayload(BaseModel):
    """`ERROR` payload: {code, message} (ARCHITECTURE.md §4 / §4.1)."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str


class UpdateSettingsPayload(BaseModel):
    """`UPDATE_SETTINGS` (host): partial config change (ARCHITECTURE.md §4/§9)."""

    model_config = ConfigDict(extra="forbid")

    config: MatchConfigUpdate


class SettingsUpdatePayload(BaseModel):
    """`SETTINGS_UPDATE` broadcast: the full, authoritative config (§4/§9)."""

    model_config = ConfigDict(extra="forbid")

    config: MatchConfig


class StartGamePayload(BaseModel):
    """`START_GAME` (host): start with the current config; no fields (§4)."""

    model_config = ConfigDict(extra="forbid")


class SubmitHandPayload(BaseModel):
    """`SUBMIT_HAND` (alive player): a hand for the current round (§4).

    `segment_id` is the TOURNAMENT pair selector; NORMAL omits it / sends null.
    """

    model_config = ConfigDict(extra="forbid")

    round_no: int
    hand: Hand
    segment_id: str | None = None


class NextRoundPayload(BaseModel):
    """`NEXT_ROUND` (host, MANUAL advance): no fields (§4/§6)."""

    model_config = ConfigDict(extra="forbid")


class RoundStartPayload(BaseModel):
    """`ROUND_START` broadcast: round window + authoritative timing (§4/§7.1)."""

    model_config = ConfigDict(extra="forbid")

    round_no: int
    # UTC ISO8601 (ms, trailing Z); clients derive remaining time from the diff.
    deadline_at: str
    server_now: str
    alive_player_ids: list[str]
    segment_id: str | None = None


class SubmissionUpdatePayload(BaseModel):
    """`SUBMISSION_UPDATE` broadcast: who has submitted (no hands, §4)."""

    model_config = ConfigDict(extra="forbid")

    round_no: int
    submitted_player_ids: list[str]
    expected_count: int
    segment_id: str | None = None


class RoundResultPayload(BaseModel):
    """`ROUND_RESULT` broadcast: hands revealed + outcome (§4).

    NORMAL carries no scores (`scores == {}`); the outcome is in
    `winner_ids` / `eliminated_player_ids` / `alive_player_ids` (§4 scores note).
    """

    model_config = ConfigDict(extra="forbid")

    round_no: int
    hands: dict[str, Hand]
    is_draw: bool
    winner_ids: list[str]
    eliminated_player_ids: list[str]
    alive_player_ids: list[str]
    scores: dict[str, int]
    segment_id: str | None = None


class MatchEndPayload(BaseModel):
    """`MATCH_END` broadcast: final winners and the reason (§4)."""

    model_config = ConfigDict(extra="forbid")

    match_id: str
    winner_ids: list[str]
    scores: dict[str, int]
    reason: MatchEndReason


class LeavePayload(BaseModel):
    """`LEAVE` (self): no fields (§4)."""

    model_config = ConfigDict(extra="forbid")


class AddCpuPayload(BaseModel):
    """`ADD_CPU` (host, lobby only): add demo CPU players (§4/§6)."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=1, ge=1, le=ROOM_CAPACITY)
    strategy: CpuStrategy = CpuStrategy.RANDOM


class RemoveCpuPayload(BaseModel):
    """`REMOVE_CPU` (host, lobby only): remove a CPU or the last-added CPU (§4)."""

    model_config = ConfigDict(extra="forbid")

    player_id: str | None = None


class ReturnToLobbyPayload(BaseModel):
    """`RETURN_TO_LOBBY` (host, from MATCH_END): no fields (§4/§6)."""

    model_config = ConfigDict(extra="forbid")


class PlayerJoinedPayload(BaseModel):
    """`PLAYER_JOINED` broadcast: UX notification; LOBBY_UPDATE is authoritative (§4)."""

    model_config = ConfigDict(extra="forbid")

    player: PlayerView


class PlayerLeftPayload(BaseModel):
    """`PLAYER_LEFT` broadcast: UX notification; LOBBY_UPDATE is authoritative (§4)."""

    model_config = ConfigDict(extra="forbid")

    player_id: str


class HostChangedPayload(BaseModel):
    """`HOST_CHANGED` broadcast: UX notification; host authority is LOBBY_UPDATE (§4)."""

    model_config = ConfigDict(extra="forbid")

    host_player_id: str
