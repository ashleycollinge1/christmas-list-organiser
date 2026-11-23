"""Shared helpers: input cleaning, app settings and season lookup."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, Season

DEFAULT_SETTINGS: dict[str, object] = {
    # +/- this many pence of the budget counts as "on budget".
    "budget_margin_pence": 500,
}


def clean(value: str | None) -> str | None:
    """Strip whitespace; empty strings become None (optional fields)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg)


_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:(?!\d)", re.I)  # "mailto:", "javascript:", but not "host:443"


def clean_link(value: str | None) -> str | None:
    value = clean(value)
    if value is None:
        return None
    if not _SCHEME.match(value):
        value = "https://" + value
    if not value.lower().startswith(("http://", "https://")):
        raise unprocessable("Links must start with http:// or https://.")
    if any(c.isspace() for c in value):
        raise unprocessable("Links can't contain spaces.")
    return value


def get_setting(db: Session, key: str):
    row = db.get(AppSetting, key)
    return row.value if row is not None else DEFAULT_SETTINGS[key]


def all_settings(db: Session) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for row in db.scalars(select(AppSetting)).all():
        if row.key in out:
            out[row.key] = row.value
    return out


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def margin(db: Session) -> int:
    return int(get_setting(db, "budget_margin_pence"))


def active_season(db: Session) -> Season | None:
    return db.scalar(select(Season).where(Season.is_archived.is_(False)))


def ensure_active_season(db: Session) -> Season:
    """There is always an active season; the first one is named after the current year."""
    season = active_season(db)
    if season is None:
        season = Season(name=f"Christmas {datetime.now(UTC).year}")
        db.add(season)
        db.commit()
    return season


def season_out(s: Season) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "is_archived": s.is_archived,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "archived_at": s.archived_at.isoformat() if s.archived_at else None,
    }
