"""Recipients, gifts and the season overview.

Visibility: a recipient is visible only to its owner and the users it is shared
with. Admins get no special access here, so "hidden from" holds for everyone.
Archived seasons are read-only.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..budget import Totals, gift_cost, line_total
from ..common import clean, clean_link, ensure_active_season, margin, season_out, unprocessable
from ..db import get_db
from ..models import (
    PRIORITY_MEDIUM,
    STATUS_IDEA,
    STATUS_ORDERED,
    STATUSES,
    Category,
    Gift,
    Recipient,
    RecipientShare,
    Season,
    User,
)
from ..security import current_user

router = APIRouter(prefix="/api", tags=["lists"])

MAX_PENCE = 10_000_000  # GBP 100,000
STATUS_RANK = {s: i for i, s in enumerate(STATUSES)}


# --------------------------------------------------------------------------- access


def _visible(user: User):
    shared = select(RecipientShare.recipient_id).where(RecipientShare.user_id == user.id)
    return or_(Recipient.owner_id == user.id, Recipient.id.in_(shared))


def _season_or_404(db: Session, season_id: int | None) -> Season:
    if season_id is None:
        return ensure_active_season(db)
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found.")
    return season


def _writable(season: Season) -> None:
    if season.is_archived:
        raise HTTPException(status.HTTP_409_CONFLICT, "This season is archived and read-only.")


def load_recipient(db: Session, user: User, recipient_id: int, *, write: bool = False) -> Recipient:
    r = db.scalar(select(Recipient).where(Recipient.id == recipient_id, _visible(user)))
    if r is None:
        raise HTTPException(404, "Recipient not found.")
    if write:
        _writable(db.get(Season, r.season_id))
    return r


def load_gift(db: Session, user: User, gift_id: int, *, write: bool = False) -> Gift:
    g = db.get(Gift, gift_id)
    if g is None:
        raise HTTPException(404, "Gift not found.")
    load_recipient(db, user, g.recipient_id, write=write)
    return g


def _member_ids(r: Recipient) -> set[int]:
    return {r.owner_id, *(s.user_id for s in r.shares)}


# --------------------------------------------------------------------------- output


def _person(u: User | None) -> dict | None:
    return {"id": u.id, "name": u.name} if u else None


def gift_out(g: Gift) -> dict:
    return {
        "id": g.id,
        "recipient_id": g.recipient_id,
        "description": g.description,
        "link": g.link,
        "price_pence": g.price_pence,
        "quantity": g.quantity,
        "my_share_pence": g.my_share_pence,
        "line_total_pence": line_total(g),
        "cost_pence": gift_cost(g),
        "priority": g.priority,
        "status": g.status,
        "notes": g.notes,
        "buyer": _person(g.buyer),
        "retailer": g.retailer,
        "tracking_number": g.tracking_number,
        "delivery_date": g.delivery_date.isoformat() if g.delivery_date else None,
        "hiding_place": g.hiding_place,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
    }


def sorted_gifts(gifts: list[Gift]) -> list[Gift]:
    return sorted(gifts, key=lambda g: (STATUS_RANK.get(g.status, 99), g.priority, g.id))


def recipient_out(r: Recipient, user: User, m: int, read_only: bool, with_gifts: bool = True) -> dict:
    totals = Totals(budget=r.budget_pence).add_gifts(r.gifts)
    out = {
        "id": r.id,
        "season_id": r.season_id,
        "name": r.name,
        "budget_pence": r.budget_pence,
        "notes": r.notes,
        "category": {"id": r.category.id, "name": r.category.name} if r.category else None,
        "owner": _person(r.owner),
        "is_owner": r.owner_id == user.id,
        "shared_with": sorted((_person(s.user) for s in r.shares), key=lambda p: p["name"].lower()),
        "read_only": read_only,
        "totals": totals.to_dict(m),
    }
    if with_gifts:
        out["gifts"] = [gift_out(g) for g in sorted_gifts(r.gifts)]
    return out


# --------------------------------------------------------------------------- overview


@router.get("/overview")
def overview(
    season_id: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    season = _season_or_404(db, season_id)
    m = margin(db)
    recipients = db.scalars(
        select(Recipient)
        .where(Recipient.season_id == season.id, _visible(user))
        .order_by(func.lower(Recipient.name), Recipient.id)
    ).all()
    categories = db.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()

    groups: dict[int | None, dict] = {
        c.id: {"category": {"id": c.id, "name": c.name}, "totals": Totals(), "recipients": []} for c in categories
    }
    groups[None] = {"category": None, "totals": Totals(), "recipients": []}
    season_totals = Totals()
    to_order, awaiting = [], []

    for r in recipients:
        out = recipient_out(r, user, m, season.is_archived)
        rt = Totals(budget=r.budget_pence).add_gifts(r.gifts)
        g = groups[r.category_id if r.category_id in groups else None]
        g["recipients"].append(out)
        g["totals"].merge(rt)
        season_totals.merge(rt)
        for gift in r.gifts:
            row = {**gift_out(gift), "recipient_name": r.name}
            if gift.status == STATUS_IDEA:
                to_order.append(row)
            elif gift.status == STATUS_ORDERED:
                awaiting.append(row)

    to_order.sort(key=lambda x: (x["priority"], x["recipient_name"].lower(), x["id"]))
    awaiting.sort(key=lambda x: (x["delivery_date"] or "9999-12-31", x["recipient_name"].lower(), x["id"]))

    return {
        "season": season_out(season),
        "read_only": season.is_archived,
        "margin_pence": m,
        "totals": season_totals.to_dict(m),
        "groups": [{**g, "totals": g["totals"].to_dict(m)} for g in groups.values() if g["recipients"]],
        "to_order": to_order,
        "awaiting_delivery": awaiting,
    }


# --------------------------------------------------------------------------- recipients


class RecipientIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    budget_pence: int | None = Field(default=None, ge=0, le=MAX_PENCE)
    notes: str | None = Field(default=None, max_length=4000)
    category_id: int | None = None


class SharesIn(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=50)


def _check_category(db: Session, category_id: int | None) -> None:
    if category_id is not None and db.get(Category, category_id) is None:
        raise unprocessable("That category no longer exists.")


@router.post("/recipients", status_code=201)
def create_recipient(body: RecipientIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    season = ensure_active_season(db)
    name = clean(body.name)
    if not name:
        raise unprocessable("Give the recipient a name.")
    _check_category(db, body.category_id)
    r = Recipient(
        season_id=season.id,
        owner_id=user.id,
        name=name,
        budget_pence=body.budget_pence,
        notes=clean(body.notes),
        category_id=body.category_id,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"recipient": recipient_out(r, user, margin(db), False)}


@router.get("/recipients/{recipient_id}")
def get_recipient(recipient_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    r = load_recipient(db, user, recipient_id)
    season = db.get(Season, r.season_id)
    return {
        "recipient": recipient_out(r, user, margin(db), season.is_archived),
        "season": season_out(season),
    }


@router.patch("/recipients/{recipient_id}")
def update_recipient(
    recipient_id: int, body: RecipientIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    r = load_recipient(db, user, recipient_id, write=True)
    fields = body.model_fields_set
    if "name" in fields:
        name = clean(body.name)
        if not name:
            raise unprocessable("Give the recipient a name.")
        r.name = name
    if "budget_pence" in fields:
        r.budget_pence = body.budget_pence
    if "notes" in fields:
        r.notes = clean(body.notes)
    if "category_id" in fields:
        _check_category(db, body.category_id)
        r.category_id = body.category_id
    db.commit()
    db.refresh(r)
    return {"recipient": recipient_out(r, user, margin(db), False)}


@router.delete("/recipients/{recipient_id}")
def delete_recipient(recipient_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    r = load_recipient(db, user, recipient_id, write=True)
    if r.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who added this recipient can delete them.")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.put("/recipients/{recipient_id}/shares")
def set_shares(
    recipient_id: int, body: SharesIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    r = load_recipient(db, user, recipient_id, write=True)
    if r.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who added this recipient can change sharing.")
    ids = set(body.user_ids) - {r.owner_id}
    if ids:
        found = set(db.scalars(select(User.id).where(User.id.in_(ids), User.is_active.is_(True))).all())
        if found != ids:
            raise unprocessable("Some of those people don't exist or are deactivated.")
    current = {s.user_id: s for s in r.shares}
    for uid in set(current) - ids:
        r.shares.remove(current[uid])
    for uid in ids - set(current):
        r.shares.append(RecipientShare(user_id=uid))
    db.commit()
    db.refresh(r)
    return {"recipient": recipient_out(r, user, margin(db), False)}


# --------------------------------------------------------------------------- gifts


class GiftIn(BaseModel):
    description: str | None = Field(default=None, max_length=200)
    link: str | None = Field(default=None, max_length=2048)
    price_pence: int | None = Field(default=None, ge=0, le=MAX_PENCE)
    quantity: int | None = Field(default=None, ge=1, le=99)
    my_share_pence: int | None = Field(default=None, ge=0, le=MAX_PENCE)
    priority: int | None = Field(default=None, ge=1, le=3)
    status: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    buyer_id: int | None = None
    retailer: str | None = Field(default=None, max_length=120)
    tracking_number: str | None = Field(default=None, max_length=120)
    delivery_date: date | None = None
    hiding_place: str | None = Field(default=None, max_length=160)


TEXT_FIELDS = ("notes", "retailer", "tracking_number", "hiding_place")


def _apply_gift(g: Gift, body: GiftIn, r: Recipient, fields: set[str]) -> None:
    if "description" in fields:
        desc = clean(body.description)
        if not desc:
            raise unprocessable("Describe the gift.")
        g.description = desc
    if "link" in fields:
        g.link = clean_link(body.link)
    for f in ("price_pence", "my_share_pence", "delivery_date"):
        if f in fields:
            setattr(g, f, getattr(body, f))
    if "quantity" in fields:
        g.quantity = body.quantity or 1
    if "priority" in fields:
        g.priority = body.priority or PRIORITY_MEDIUM
    if "status" in fields:
        if body.status not in STATUSES:
            raise unprocessable(f"Status must be one of: {', '.join(STATUSES)}.")
        g.status = body.status
    for f in TEXT_FIELDS:
        if f in fields:
            setattr(g, f, clean(getattr(body, f)))
    if "buyer_id" in fields:
        if body.buyer_id is not None and body.buyer_id not in _member_ids(r):
            raise unprocessable("The buyer must be someone this recipient is shared with.")
        g.buyer_id = body.buyer_id


@router.post("/recipients/{recipient_id}/gifts", status_code=201)
def create_gift(
    recipient_id: int, body: GiftIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    r = load_recipient(db, user, recipient_id, write=True)
    fields = set(body.model_fields_set) | {"description"}
    g = Gift(recipient_id=r.id, buyer_id=user.id, status=STATUS_IDEA, priority=PRIORITY_MEDIUM, quantity=1)
    _apply_gift(g, body, r, fields)
    db.add(g)
    db.commit()
    db.refresh(g)
    db.refresh(r)
    return {"gift": gift_out(g), "recipient": recipient_out(r, user, margin(db), False, with_gifts=False)}


@router.patch("/gifts/{gift_id}")
def update_gift(gift_id: int, body: GiftIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = load_gift(db, user, gift_id, write=True)
    r = g.recipient
    _apply_gift(g, body, r, set(body.model_fields_set))
    db.commit()
    db.refresh(g)
    db.refresh(r)
    return {"gift": gift_out(g), "recipient": recipient_out(r, user, margin(db), False, with_gifts=False)}


@router.delete("/gifts/{gift_id}")
def delete_gift(gift_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    g = load_gift(db, user, gift_id, write=True)
    r = g.recipient
    db.delete(g)
    db.commit()
    db.refresh(r)
    return {"ok": True, "recipient": recipient_out(r, user, margin(db), False, with_gifts=False)}
