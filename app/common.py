"""Shared helpers: input cleaning, app settings and season lookup."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, Occasion, User

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


def occasion_out(o: Occasion, user: User | None = None) -> dict:
    return {
        "id": o.id,
        "name": o.name,
        "kind": o.kind,
        "date": o.occasion_date.isoformat() if o.occasion_date else None,
        "is_archived": o.is_archived,
        "created_by": {"id": o.created_by.id, "name": o.created_by.name} if o.created_by else None,
        "can_manage": user is not None and can_manage(o, user),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "archived_at": o.archived_at.isoformat() if o.archived_at else None,
    }


def can_manage(o: Occasion, user: User) -> bool:
    """Rename, archive, unarchive and delete: the creator, or an admin if the creator is gone."""
    return o.created_by_id == user.id or (o.created_by_id is None and user.is_admin)


def bootstrap_first_occasion(db: Session) -> None:
    """A brand-new install starts with this year's Christmas, created by the first admin."""
    if db.scalar(select(Occasion.id).limit(1)) is not None:
        return
    admin = db.scalar(select(User).where(User.role == "admin").order_by(User.id))
    if admin is None:
        return
    db.add(Occasion(name=f"Christmas {datetime.now(UTC).year}", kind="christmas", created_by_id=admin.id))
    db.commit()
