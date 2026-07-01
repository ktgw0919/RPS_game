"""MongoDB connection (PyMongo Async: AsyncMongoClient).

Uses the official async API (`AsyncMongoClient`); Motor is intentionally not
adopted (ARCHITECTURE.md §1). Only confirmed results (match history) are
persisted here; live game state stays in the in-memory store.
"""

from __future__ import annotations

from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings

# MongoDB documents are plain dictionaries at this layer.
MongoDoc = dict[str, Any]


class Database:
    """Owns the AsyncMongoClient lifecycle, created/closed by the app lifespan."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.client: AsyncMongoClient[MongoDoc] | None = None
        self.db: AsyncDatabase[MongoDoc] | None = None

    async def connect(self) -> None:
        # Bounded server selection so a missing DB fails fast instead of hanging
        # (the app continues with in-memory state; persistence degrades).
        self.client = AsyncMongoClient(self._settings.db_url, serverSelectionTimeoutMS=3000)
        self.db = self.client[self._settings.db_name]

    async def ping(self) -> None:
        """Verify connectivity (raises if the server is unreachable)."""
        if self.client is None:
            raise RuntimeError("Database.connect() must be called before ping().")
        await self.client.admin.command("ping")

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
            self.client = None
            self.db = None
