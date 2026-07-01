"""Match history persistence (ARCHITECTURE.md §5/§6).

Writes finalized match results to the `match_history` MongoDB collection when a
match reaches MATCH_END. Live game state stays in-memory; this layer only stores
the authoritative snapshot at end-of-match.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.constants import MATCH_HISTORY_MAX_LIMIT
from app.models import (
    Match,
    MatchHistoryEntry,
    MatchHistoryListResponse,
    MatchHistoryPlayerEntry,
    Player,
    Room,
    RuleType,
)

logger = logging.getLogger("rps.match_history")

COLLECTION_NAME = "match_history"


class HistoryUnavailableError(Exception):
    """Raised when match history cannot be read (e.g. MongoDB unavailable)."""


class MatchHistoryRecord(BaseModel):
    """Document shape for `match_history` (ARCHITECTURE.md §6)."""

    model_config = ConfigDict(extra="forbid")

    room_code: str
    match_id: str
    rule_type: RuleType
    players: list[MatchHistoryPlayerEntry]
    winner_ids: list[str] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    started_at: datetime
    ended_at: datetime


def build_match_history_record(room: Room, match: Match) -> MatchHistoryRecord | None:
    """Build a persistable record from a finished match, or None if incomplete."""
    if match.started_at is None or match.ended_at is None:
        return None
    players = players_for_history(room, match.participant_player_ids)
    if not players:
        return None
    return MatchHistoryRecord(
        room_code=room.room_code.upper(),
        match_id=match.match_id,
        rule_type=match.rule_type,
        players=players,
        winner_ids=list(match.winner_ids),
        scores=dict(match.scores),
        started_at=match.started_at,
        ended_at=match.ended_at,
    )


def players_for_history(room: Room, participant_ids: list[str]) -> list[MatchHistoryPlayerEntry]:
    """Map participant ids to display rows using the room member snapshot."""
    entries: list[MatchHistoryPlayerEntry] = []
    for player_id in participant_ids:
        member = room.members.get(player_id)
        if member is None:
            continue
        entries.append(_player_entry(member))
    return entries


def _player_entry(player: Player) -> MatchHistoryPlayerEntry:
    return MatchHistoryPlayerEntry(
        player_id=player.player_id,
        display_name=player.display_name,
        is_cpu=player.is_cpu,
    )


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(UTC)
    raise TypeError(f"unsupported datetime value: {value!r}")


def _doc_to_entry(doc: dict[str, Any]) -> MatchHistoryEntry:
    players_raw = doc.get("players", [])
    return MatchHistoryEntry(
        match_id=str(doc["match_id"]),
        rule_type=RuleType(doc["rule_type"]),
        players=[MatchHistoryPlayerEntry.model_validate(p) for p in players_raw],
        winner_ids=list(doc.get("winner_ids", [])),
        scores={str(k): int(v) for k, v in doc.get("scores", {}).items()},
        started_at=_coerce_datetime(doc["started_at"]),
        ended_at=_coerce_datetime(doc["ended_at"]),
    )


class MatchHistoryRepository:
    """Persists finalized matches to MongoDB (degrades gracefully when DB is down)."""

    def __init__(self, db: AsyncDatabase[dict[str, Any]] | None) -> None:
        self._db = db

    async def ensure_indexes(self) -> None:
        """Create indexes for room-scoped history queries (§6)."""
        if self._db is None:
            return
        collection = self._db[COLLECTION_NAME]
        await collection.create_index([("room_code", 1), ("ended_at", -1)])
        await collection.create_index("match_id", unique=True)

    async def save_finished_match(self, room: Room, match: Match) -> None:
        """Insert one finished match document (no-op when DB is unavailable)."""
        if self._db is None:
            logger.warning("Skipping match history persist: database not connected.")
            return
        record = build_match_history_record(room, match)
        if record is None:
            logger.warning(
                "Skipping match history persist for %s: incomplete match %s.",
                room.room_code,
                match.match_id,
            )
            return
        doc = record.model_dump(mode="json")
        # Keep BSON datetimes for started_at / ended_at (mode=json serializes to str).
        doc["started_at"] = record.started_at
        doc["ended_at"] = record.ended_at
        doc["rule_type"] = record.rule_type.value
        try:
            await self._db[COLLECTION_NAME].insert_one(doc)
        except DuplicateKeyError:
            logger.warning("Match history already stored for match_id=%s.", match.match_id)
        except Exception:
            logger.exception(
                "Failed to persist match history for room=%s match_id=%s.",
                room.room_code,
                match.match_id,
            )

    async def list_by_room(self, room_code: str, *, limit: int) -> MatchHistoryListResponse:
        """Return finished matches for a room, newest first (ARCHITECTURE.md §3.1)."""
        if self._db is None:
            raise HistoryUnavailableError("database not connected")
        bounded = max(1, min(limit, MATCH_HISTORY_MAX_LIMIT))
        collection = self._db[COLLECTION_NAME]
        try:
            cursor = collection.find({"room_code": room_code.upper()}).sort("ended_at", -1)
            docs = await cursor.to_list(length=bounded + 1)
        except Exception as exc:
            logger.exception("Failed to list match history for room=%s.", room_code)
            raise HistoryUnavailableError("query failed") from exc

        has_more = len(docs) > bounded
        entries = [_doc_to_entry(doc) for doc in docs[:bounded]]
        return MatchHistoryListResponse(
            room_code=room_code.upper(),
            matches=entries,
            has_more=has_more,
        )
