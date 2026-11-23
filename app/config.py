"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = os.environ.get("POSTGRES_USER", "xmas")
    password = os.environ.get("POSTGRES_PASSWORD", "xmas")
    host = os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "xmas")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=_database_url)
    frontend_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("FRONTEND_DIR", str(Path(__file__).resolve().parent.parent / "frontend"))
        )
    )

    admin_username: str = field(default_factory=lambda: os.environ.get("ADMIN_USERNAME", "admin"))
    admin_password: str = field(default_factory=lambda: os.environ.get("ADMIN_PASSWORD", ""))

    # Set to false only when serving over plain HTTP (e.g. local dev).
    cookie_secure: bool = field(default_factory=lambda: _bool("COOKIE_SECURE", True))
    session_days: int = field(default_factory=lambda: _int("SESSION_DAYS", 30))
    min_password_length: int = field(default_factory=lambda: _int("MIN_PASSWORD_LENGTH", 12))
    login_max_failures: int = field(default_factory=lambda: _int("LOGIN_MAX_FAILURES", 5))
    login_window_seconds: int = field(default_factory=lambda: _int("LOGIN_WINDOW_SECONDS", 900))
    invite_days: int = field(default_factory=lambda: _int("INVITE_DAYS", 7))

    app_version: str = field(default_factory=lambda: os.environ.get("APP_VERSION", "dev"))


settings = Settings()
