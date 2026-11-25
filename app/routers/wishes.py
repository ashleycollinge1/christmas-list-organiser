"""Your own wish list: things you'd like, Anytime or for a specific occasion.

Private to you. Wishes never count towards spending, budgets or wrapping.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import linkpreview
from ..common import clean, clean_link, unprocessable
from ..db import get_db
from ..models import PERSON_ME, PRIORITY_MEDIUM, Person, User, Wish
from ..security import current_user
from .lists import MAX_PENCE, load_occasion

router = APIRouter(prefix="/api/wishes", tags=["wishes"])


class WishIn(BaseModel):
    description: str | None = Field(default=None, max_length=200)
    link: str | None = Field(default=None, max_length=2048)
    price_pence: int | None = Field(default=None, ge=0, le=MAX_PENCE)
    quantity: int | None = Field(default=None, ge=1, le=99)
    priority: int | None = Field(default=None, ge=1, le=3)
    notes: str | None = Field(default=None, max_length=4000)
    occasion_id: int | None = None  # None = Anytime
    archived: bool | None = None


def my_person(db: Session, user: User) -> Person | None:
    return db.scalar(select(Person).where(Person.owner_id == user.id, Person.kind == PERSON_ME))


def ensure_me(db: Session, user: User) -> Person:
    """Your "me" person, created on first use and named after you."""
    me = my_person(db, user)
    if me is None:
        me = Person(owner_id=user.id, kind=PERSON_ME, name=user.name)
        db.add(me)
        db.flush()
    return me


def line_total(w: Wish) -> int | None:
    return None if w.price_pence is None else w.price_pence * w.quantity


def wish_out(w: Wish) -> dict:
    o = w.occasion
    return {
        "id": w.id,
        "description": w.description,
        "link": w.link,
        "price_pence": w.price_pence,
        "quantity": w.quantity,
        "line_total_pence": line_total(w),
        "priority": w.priority,
        "notes": w.notes,
        "occasion": {"id": o.id, "name": o.name, "kind": o.kind, "is_archived": o.is_archived} if o else None,
        "archived": w.archived_at is not None,
        "archived_at": w.archived_at.isoformat() if w.archived_at else None,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


def summarise(wishes: list[Wish]) -> dict:
    active = [w for w in wishes if w.archived_at is None]
    return {
        "count": len(active),
        "total_pence": sum(line_total(w) or 0 for w in active),
        "unpriced": sum(1 for w in active if w.price_pence is None),
    }


def sort_key(w: Wish):
    return (w.priority, w.id)


def occasion_wishes(db: Session, user: User, occasion_id: int) -> dict | None:
    """Summary of your wishes for one occasion, for its overview page."""
    me = my_person(db, user)
    if me is None:
        return None
    wishes = sorted(
        db.scalars(
            select(Wish).where(Wish.owner_id == user.id, Wish.occasion_id == occasion_id, Wish.archived_at.is_(None))
        ).all(),
        key=sort_key,
    )
    return {**summarise(wishes), "items": [wish_out(w) for w in wishes[:3]]}


def _mine(db: Session, user: User, wish_id: int) -> Wish:
    w = db.get(Wish, wish_id)
    if w is None or w.owner_id != user.id:
        raise HTTPException(404, "Wish not found.")
    return w


def _apply(db: Session, user: User, w: Wish, body: WishIn, fields: set[str]) -> None:
    if "description" in fields:
        desc = clean(body.description)
        if not desc:
            raise unprocessable("Describe what you'd like.")
        w.description = desc
    if "link" in fields:
        w.link = clean_link(body.link)
    if "price_pence" in fields:
        w.price_pence = body.price_pence
    if "quantity" in fields:
        w.quantity = body.quantity or 1
    if "priority" in fields:
        w.priority = body.priority or PRIORITY_MEDIUM
    if "notes" in fields:
        w.notes = clean(body.notes)
    if "occasion_id" in fields:
        # Moving needs an occasion you can see; archived ones are fine (it's your own list).
        w.occasion_id = None if body.occasion_id is None else load_occasion(db, user, body.occasion_id).id
    if "archived" in fields and body.archived is not None:
        w.archived_at = datetime.now(UTC) if body.archived else None


class _PerUserLimit:
    """At most `limit` link reads per user per minute (the server fetches each one)."""

    def __init__(self, limit: int = 20, window: float = 60.0) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[user_id]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


preview_limit = _PerUserLimit()


@router.get("/preview")
def link_preview(
    url: str | None = Query(default=None, max_length=4096),
    text: str | None = Query(default=None, max_length=4096),
    user: User = Depends(current_user),
) -> dict:
    """Suggest a name and price for a shared link. Never fails hard: errors come back as `error`."""
    target = linkpreview.extract_url(url) or linkpreview.extract_url(text)
    if not target:
        raise unprocessable("No web link found in what was shared.")
    if not preview_limit.allow(user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many links at once. Try again in a minute.")
    try:
        return {"preview": linkpreview.preview(target).to_dict(), "error": None, "guessed": False}
    except linkpreview.PreviewError as exc:
        # Couldn't read the page (often a shop blocking automated requests): guess a name from the link.
        guess = linkpreview.name_from_url(target)
        return {
            "preview": {"url": target, "title": guess, "price_pence": None, "currency": None, "site": None},
            "error": str(exc),
            "guessed": guess is not None,
        }


@router.get("")
def list_wishes(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    me = my_person(db, user)
    wishes = sorted(db.scalars(select(Wish).where(Wish.owner_id == user.id)).all(), key=sort_key)
    return {
        "me": {"id": me.id, "name": me.name, "notes": me.notes} if me else None,
        "totals": summarise(wishes),
        "wishes": [wish_out(w) for w in wishes],
    }


@router.post("", status_code=201)
def create_wish(body: WishIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    me = ensure_me(db, user)
    w = Wish(owner_id=user.id, person_id=me.id, quantity=1, priority=PRIORITY_MEDIUM)
    _apply(db, user, w, body, set(body.model_fields_set) | {"description"})
    db.add(w)
    db.commit()
    db.refresh(w)
    return {"wish": wish_out(w)}


@router.patch("/{wish_id}")
def update_wish(wish_id: int, body: WishIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = _mine(db, user, wish_id)
    _apply(db, user, w, body, set(body.model_fields_set))
    db.commit()
    db.refresh(w)
    return {"wish": wish_out(w)}


@router.delete("/{wish_id}")
def delete_wish(wish_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    w = _mine(db, user, wish_id)
    db.delete(w)
    db.commit()
    return {"ok": True}


class WishBulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(move|archive|restore|delete)$")
    occasion_id: int | None = None  # move: None = Anytime


@router.post("/bulk")
def bulk_wishes(body: WishBulkIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Apply one action to several of your wishes, all or nothing."""
    wishes = [_mine(db, user, wid) for wid in dict.fromkeys(body.ids)]
    if body.action == "move":
        target = None if body.occasion_id is None else load_occasion(db, user, body.occasion_id).id
        for w in wishes:
            w.occasion_id = target
    elif body.action in ("archive", "restore"):
        now = datetime.now(UTC)
        for w in wishes:
            w.archived_at = (w.archived_at or now) if body.action == "archive" else None
    else:
        for w in wishes:
            db.delete(w)
    db.commit()
    return {"ok": True, "count": len(wishes)}
