# RPS Backend

FastAPI + WebSocket + MongoDB backend for the realtime Rock-Paper-Scissors game.
Dependency management uses `uv` (`pyproject.toml`). See `../docs/ARCHITECTURE.md`
for the authoritative design.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- MongoDB (local via Docker, or MongoDB Atlas)

## Setup

```powershell
# from backend/
uv sync --all-extras   # installs deps + dev tools (omit --all-extras to skip redis)
Copy-Item .env.example .env   # then edit DB_URL / DB_NAME
```

### MongoDB

Two options (switch via `backend/.env`):

- **Local (docker-compose)** — from the repo root: `docker compose up -d`,
  then `DB_URL=mongodb://localhost:27017`, `DB_NAME=rps`.
- **MongoDB Atlas** — set `DB_URL` to your Atlas connection string.

The app starts even if MongoDB is briefly unreachable (live state is in-memory);
only match-history persistence degrades until the DB is reachable.

## Run

```powershell
# single worker (MVP: in-memory game state is authoritative)
uv run uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/health`.

## Quality

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

## Layout (ARCHITECTURE.md §2)

```
app/
  main.py        # entrypoint, CORS, lifespan, routers
  config.py      # settings (python-decouple), fail-fast on required values
  database.py    # MongoDB connection (PyMongo Async: AsyncMongoClient)
  models.py      # Pydantic v2 schemas + domain models + ErrorCode
  errors.py      # AppError + REST error handler
  utils.py       # generic helpers (time formatting, room code)
  routers/       # rooms.py (REST), ws.py (WebSocket)
  core/          # constants, security, state_store, connection_manager, lifecycle, round_runner, match_history, rate_limit
  game/          # engine, cpu, start_conditions (rules/: Phase 3)
```
