"""FastAPI entrypoint: lifespan, CORS, routers (ARCHITECTURE.md §1/§2).

The app lifecycle is managed with `lifespan` (not `@app.on_event`). On startup
we validate settings (fail-fast), connect to MongoDB, and initialize the
in-memory game state store. On shutdown we close the DB connection.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.connection_manager import ConnectionManager
from app.core.lifecycle import LifecycleManager
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.round_runner import RoundRunner
from app.core.state_store import InMemoryGameStateStore
from app.database import Database
from app.errors import register_error_handlers
from app.models import PublicConfigResponse
from app.routers import rooms, ws

logger = logging.getLogger("rps")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Fail-fast: missing/invalid required settings raise here.
    settings = get_settings()
    app.state.settings = settings

    app.state.store = InMemoryGameStateStore()
    app.state.connection_manager = ConnectionManager()
    app.state.round_runner = RoundRunner(app.state.store, app.state.connection_manager)
    app.state.lifecycle = LifecycleManager(app.state.store, app.state.connection_manager, settings)
    app.state.room_create_limiter = SlidingWindowRateLimiter(
        max_events=settings.room_create_rate_max,
        window_sec=settings.room_create_rate_window_sec,
    )

    database = Database(settings)
    await database.connect()
    try:
        await database.ping()
        logger.info("Connected to MongoDB '%s'.", settings.db_name)
    except Exception:
        # Don't crash the app on a transient DB hiccup; live state is in-memory.
        # Persistence (match history) degrades until the DB is reachable again.
        logger.exception("MongoDB ping failed at startup; continuing.")
    app.state.database = database

    app.state.lifecycle.start()
    try:
        yield
    finally:
        await app.state.lifecycle.stop()
        await app.state.round_runner.shutdown()
        await database.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Rock-Paper-Scissors API", version="0.1.0", lifespan=lifespan)

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(rooms.router)
    app.include_router(ws.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config", tags=["meta"])
    async def public_config(request: Request) -> PublicConfigResponse:
        """Client-visible server flags (e.g. demo CPU toggle)."""
        app_settings = request.app.state.settings
        return PublicConfigResponse(allow_cpu=app_settings.allow_cpu)

    return app


app = create_app()
