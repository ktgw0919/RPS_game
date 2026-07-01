"""Tests for match history persistence (ARCHITECTURE.md §6)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.core.match_history import (
    HistoryUnavailableError,
    MatchHistoryRepository,
    build_match_history_record,
    players_for_history,
)
from app.models import (
    ConnectionState,
    Match,
    MatchConfig,
    MatchState,
    NormalEndMode,
    Player,
    Room,
    RoomStatus,
    RuleType,
)

NOW = datetime(2026, 6, 29, 8, 0, 0, tzinfo=UTC)


def _player(player_id: str, *, display_name: str | None = None, is_cpu: bool = False) -> Player:
    return Player(
        player_id=player_id,
        token=None if is_cpu else "tok",
        display_name=display_name or player_id,
        connection_state=ConnectionState.CONNECTED,
        is_cpu=is_cpu,
        joined_at=NOW,
    )


def _room_with_match(*player_ids: str) -> tuple[Room, Match]:
    host = _player(player_ids[0], display_name="Host")
    host.is_host = True
    members = {host.player_id: host}
    for pid in player_ids[1:]:
        members[pid] = _player(pid, display_name=pid.title())
    room = Room(
        room_code="ABCD",
        host_player_id=host.player_id,
        status=RoomStatus.IN_GAME,
        members=members,
        created_at=NOW,
        last_active_at=NOW,
    )
    match = Match(
        match_id="match-1",
        rule_type=RuleType.NORMAL,
        state=MatchState.MATCH_END,
        config=MatchConfig(rule_type=RuleType.NORMAL, normal_end_mode=NormalEndMode.SINGLE_ROUND),
        alive_player_ids=[player_ids[0]],
        participant_player_ids=list(player_ids),
        winner_ids=[player_ids[0]],
        started_at=NOW,
        ended_at=NOW,
    )
    room.match = match
    return room, match


def test_build_match_history_record_maps_participants() -> None:
    room, match = _room_with_match("p1", "p2")
    record = build_match_history_record(room, match)
    assert record is not None
    assert record.room_code == "ABCD"
    assert record.match_id == "match-1"
    assert record.rule_type is RuleType.NORMAL
    assert [p.player_id for p in record.players] == ["p1", "p2"]
    assert record.players[0].display_name == "Host"
    assert record.winner_ids == ["p1"]
    assert record.scores == {}


def test_build_match_history_record_returns_none_without_timestamps() -> None:
    room, match = _room_with_match("p1", "p2")
    match.ended_at = None
    assert build_match_history_record(room, match) is None


def test_players_for_history_skips_missing_members() -> None:
    room, _match = _room_with_match("p1")
    entries = players_for_history(room, ["p1", "ghost"])
    assert len(entries) == 1
    assert entries[0].player_id == "p1"


@pytest.mark.asyncio
async def test_save_finished_match_inserts_document() -> None:
    room, match = _room_with_match("p1", "p2")
    collection = MagicMock()
    collection.insert_one = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection

    repo = MatchHistoryRepository(db)
    await repo.save_finished_match(room, match)

    collection.insert_one.assert_awaited_once()
    doc = collection.insert_one.await_args.args[0]
    assert doc["room_code"] == "ABCD"
    assert doc["match_id"] == "match-1"
    assert doc["rule_type"] == "NORMAL"
    assert doc["winner_ids"] == ["p1"]
    assert len(doc["players"]) == 2
    assert doc["started_at"] == NOW
    assert doc["ended_at"] == NOW


@pytest.mark.asyncio
async def test_save_finished_match_swallows_duplicate_key() -> None:
    room, match = _room_with_match("p1", "p2")
    collection = MagicMock()
    collection.insert_one = AsyncMock(side_effect=DuplicateKeyError("dup"))
    db = MagicMock()
    db.__getitem__.return_value = collection

    repo = MatchHistoryRepository(db)
    await repo.save_finished_match(room, match)  # does not raise


@pytest.mark.asyncio
async def test_save_finished_match_no_op_without_db() -> None:
    room, match = _room_with_match("p1", "p2")
    repo = MatchHistoryRepository(None)
    await repo.save_finished_match(room, match)


@pytest.mark.asyncio
async def test_ensure_indexes_creates_expected_keys() -> None:
    collection = MagicMock()
    collection.create_index = AsyncMock()
    db = MagicMock()
    db.__getitem__.return_value = collection

    repo = MatchHistoryRepository(db)
    await repo.ensure_indexes()

    assert collection.create_index.await_count == 2
    first_call = collection.create_index.await_args_list[0].args[0]
    second_call = collection.create_index.await_args_list[1].args[0]
    assert first_call == [("room_code", 1), ("ended_at", -1)]
    assert second_call == "match_id"
    assert collection.create_index.await_args_list[1].kwargs == {"unique": True}


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs
        self._sort_field: str | None = None
        self._sort_dir = -1

    def sort(self, field: str, direction: int) -> _FakeCursor:
        self._sort_field = field
        self._sort_dir = direction
        return self

    async def to_list(self, length: int | None = None) -> list[dict]:
        docs = list(self._docs)
        if self._sort_field:
            docs.sort(key=lambda d: d[self._sort_field], reverse=self._sort_dir == -1)
        if length is None:
            return docs
        return docs[:length]


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    async def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    def find(self, query: dict) -> _FakeCursor:
        room_code = query.get("room_code")
        filtered = [d for d in self.docs if d.get("room_code") == room_code]
        return _FakeCursor(filtered)


def _repo_with_collection() -> tuple[MatchHistoryRepository, _FakeCollection]:
    collection = _FakeCollection()
    db = MagicMock()
    db.__getitem__.return_value = collection
    return MatchHistoryRepository(db), collection


@pytest.mark.asyncio
async def test_list_by_room_orders_by_ended_at_desc() -> None:
    repo, collection = _repo_with_collection()
    older = NOW.replace(hour=7)
    newer = NOW.replace(hour=9)
    collection.docs.extend(
        [
            {
                "room_code": "ABCD",
                "match_id": "old",
                "rule_type": "NORMAL",
                "players": [{"player_id": "p1", "display_name": "A", "is_cpu": False}],
                "winner_ids": [],
                "scores": {},
                "started_at": older,
                "ended_at": older,
            },
            {
                "room_code": "ABCD",
                "match_id": "new",
                "rule_type": "NORMAL",
                "players": [{"player_id": "p1", "display_name": "A", "is_cpu": False}],
                "winner_ids": [],
                "scores": {},
                "started_at": newer,
                "ended_at": newer,
            },
        ]
    )

    result = await repo.list_by_room("abcd", limit=20)

    assert result.room_code == "ABCD"
    assert [m.match_id for m in result.matches] == ["new", "old"]
    assert result.has_more is False


@pytest.mark.asyncio
async def test_list_by_room_has_more_when_at_limit() -> None:
    repo, collection = _repo_with_collection()
    for i in range(3):
        ended = NOW.replace(minute=i)
        collection.docs.append(
            {
                "room_code": "ABCD",
                "match_id": f"m{i}",
                "rule_type": "NORMAL",
                "players": [{"player_id": "p1", "display_name": "A", "is_cpu": False}],
                "winner_ids": [],
                "scores": {},
                "started_at": ended,
                "ended_at": ended,
            }
        )

    result = await repo.list_by_room("ABCD", limit=2)

    assert len(result.matches) == 2
    assert result.has_more is True


@pytest.mark.asyncio
async def test_list_by_room_raises_when_db_unavailable() -> None:
    repo = MatchHistoryRepository(None)
    with pytest.raises(HistoryUnavailableError):
        await repo.list_by_room("ABCD", limit=20)


@pytest.mark.asyncio
async def test_save_then_list_round_trip() -> None:
    room, match = _room_with_match("p1", "p2")
    repo, _collection = _repo_with_collection()
    await repo.save_finished_match(room, match)

    result = await repo.list_by_room("ABCD", limit=20)

    assert len(result.matches) == 1
    entry = result.matches[0]
    assert entry.match_id == "match-1"
    assert [p.player_id for p in entry.players] == ["p1", "p2"]
    assert entry.winner_ids == ["p1"]
