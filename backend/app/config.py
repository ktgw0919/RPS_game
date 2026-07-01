"""Application settings.

Loaded from `.env` via python-decouple and collapsed into a single `Settings`
object (ARCHITECTURE.md §1). Required values (`DB_URL`, `DB_NAME`) are validated
at import/startup time: a missing or type-invalid required value raises
immediately (fail-fast). Operational tunables have defaults and are NOT part of
the fail-fast check.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from decouple import config


class ConfigError(RuntimeError):
    """Raised at startup when a required setting is missing or invalid."""


def _required_str(key: str) -> str:
    """Read a required string setting, failing fast if missing/empty."""
    try:
        raw = config(key)
    except Exception as exc:  # decouple raises UndefinedValueError
        raise ConfigError(
            f"Required setting '{key}' is missing. Set it in backend/.env (see .env.example)."
        ) from exc
    value = str(raw).strip()
    if not value:
        raise ConfigError(f"Required setting '{key}' must not be empty.")
    return value


def _csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # --- Required (fail-fast) ---------------------------------------------
    db_url: str
    db_name: str

    # --- Optional --------------------------------------------------------
    redis_url: str | None = None
    allow_cpu: bool = True
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # --- Operational tunables (defaults; .env overridable) ----------------
    host_transfer_grace_sec: int = 30
    ghost_ttl_sec: int = 120
    room_idle_ttl_sec: int = 1800
    room_create_rate_max: int = 10
    room_create_rate_window_sec: int = 600

    @classmethod
    def load(cls) -> Settings:
        db_url = _required_str("DB_URL")
        db_name = _required_str("DB_NAME")

        redis_url_raw = config("REDIS_URL", default="")
        redis_url = str(redis_url_raw).strip() or None

        cors_raw = str(
            config(
                "CORS_ORIGINS",
                default="http://localhost:5173,http://127.0.0.1:5173",
            )
        )

        try:
            return cls(
                db_url=db_url,
                db_name=db_name,
                redis_url=redis_url,
                allow_cpu=config("ALLOW_CPU", default=True, cast=bool),
                cors_origins=_csv(cors_raw),
                host_transfer_grace_sec=config("HOST_TRANSFER_GRACE_SEC", default=30, cast=int),
                ghost_ttl_sec=config("GHOST_TTL_SEC", default=120, cast=int),
                room_idle_ttl_sec=config("ROOM_IDLE_TTL_SEC", default=1800, cast=int),
                room_create_rate_max=config("ROOM_CREATE_RATE_MAX", default=10, cast=int),
                room_create_rate_window_sec=config(
                    "ROOM_CREATE_RATE_WINDOW_SEC", default=600, cast=int
                ),
            )
        except (ValueError, TypeError) as exc:
            raise ConfigError(f"Invalid setting value: {exc}") from exc


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings, loading (and validating) on first use."""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings
