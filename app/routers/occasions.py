"""Occasions: Christmases, birthdays and anything else.

Anyone can create one. Several can be active at once. The creator can rename,
archive, unarchive and delete it.
"""

from __future__ import annotations

import datetime as dt
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget import Totals
from ..common import can_manage, clean, margin, occasion_out, unprocessable
from ..db import get_db
from ..models import (
    KINDS,
    PERSON_ME,
    STATUS_IDEA,
    STATUS_ORDERED,
    STATUS_REORDER,
    Category,
    Gift,
    Occasion,
    Person,
    Recipient,
    RecipientShare,
    User,
    Wish,
)
from ..security import current_user
from .lists import (
    MAX_PENCE,
    apply_person_fields,
    gift_out,
    load_occasion,
    recipient_out,
    set_shares,
    visible_occasion,
    visible_recipient,
)
from .wishes import ensure_me, occasion_wishes, summarise  # noqa: E402

router = APIRouter(prefix="/api/occasions", tags=["occasions"])


class OccasionIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    kind: str | None = None
    date: dt.date | None = None


class OccasionCreateIn(OccasionIn):
    # People of yours to add. With copy_from, their entry there supplies budget/sharing/gifts.
    person_ids: list[int] = Field(default_factory=list, max_length=500)
    copy_from_id: int | None = None
    copy_budgets: bool = True
    copy_sharing: bool = True
    copy_gifts: bool = False
    # "Me": the occasion is (also) for you. Your wishes with these ids move into it.
    include_me: bool = False
    wish_ids: list[int] = Field(default_factory=list, max_length=500)


class EntryIn(BaseModel):
    """Add someone to an occasion: an existing person of yours, or a new one."""

    person_id: int | None = None
    name: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=4000)
    category_id: int | None = None
    budget_pence: int | None = Field(default=None, ge=0, le=MAX_PENCE)
    share_user_ids: list[int] = Field(default_factory=list, max_length=50)


def _check_kind(kind: str | None) -> str:
    if kind not in KINDS:
        raise unprocessable(f"Type must be one of: {', '.join(KINDS)}.")
    return kind


def _manage(o: Occasion, user: User) -> None:
    if not can_manage(o, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who created this occasion can change it.")


def _visible_entries(db: Session, user: User, occasion_id: int) -> list[Recipient]:
    return list(
        db.scalars(
            select(Recipient)
            .join(Person, Recipient.person_id == Person.id)
            .where(Recipient.occasion_id == occasion_id, visible_recipient(user))
            .order_by(func.lower(Person.name), Recipient.id)
        ).all()
    )


_YEAR = re.compile(r"\b(20\d\d)\b")


def effective_date(o: Occasion) -> dt.date | None:
    """For sorting: an undated Christmas counts as 25 December of the year in its name."""
    if o.occasion_date or o.kind != "christmas":
        return o.occasion_date
    m = _YEAR.search(o.name)
    return dt.date(int(m.group(1)), 12, 25) if m else None


def _sort_key(o: Occasion):
    # Active first, soonest date first (undated last), then newest.
    return (o.is_archived, effective_date(o) or dt.date.max, -(o.created_at.timestamp() if o.created_at else 0))


# --------------------------------------------------------------------------- list & create


@router.get("")
def list_occasions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    m = margin(db)
    occasions = sorted(db.scalars(select(Occasion).where(visible_occasion(user))).all(), key=_sort_key)
    # Your own (non-archived) wishes per occasion, for occasions that are just for you.
    my_wishes: dict[int, list[Wish]] = {}
    for w in db.scalars(
        select(Wish).where(Wish.owner_id == user.id, Wish.occasion_id.is_not(None), Wish.archived_at.is_(None))
    ):
        my_wishes.setdefault(w.occasion_id, []).append(w)
    out = []
    for o in occasions:
        entries = _visible_entries(db, user, o.id)
        totals = Totals()
        for r in entries:
            totals.merge(Totals(budget=r.budget_pence).add_gifts(r.gifts))
        out.append(
            {
                **occasion_out(o, user),
                "people": len(entries),
                "totals": totals.to_dict(m),
                "my_wishes": summarise(my_wishes.get(o.id, [])),
            }
        )
    return {"occasions": out}


def _copy_entry(src: Recipient | None, target: Occasion, person: Person, body: OccasionCreateIn) -> Recipient:
    r = Recipient(occasion_id=target.id, owner_id=person.owner_id, person=person)
    r.mirror_person()
    if src is None:
        return r
    if body.copy_budgets:
        r.budget_pence = src.budget_pence
    if body.copy_sharing:
        r.shares = [RecipientShare(user_id=s.user_id) for s in src.shares if s.user.is_active]
    members = {r.owner_id, *(s.user_id for s in r.shares)}
    if body.copy_gifts:
        # The idea carries over; last time's order details don't.
        r.gifts = [
            Gift(
                description=g.description,
                link=g.link,
                price_pence=g.price_pence,
                quantity=g.quantity,
                my_share_pence=g.my_share_pence,
                priority=g.priority,
                status=STATUS_IDEA,
                notes=g.notes,
                buyer_id=g.buyer_id if g.buyer_id in members else r.owner_id,
                retailer=g.retailer,
            )
            for g in src.gifts
        ]
    return r


@router.post("", status_code=201)
def create_occasion(body: OccasionCreateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    name = clean(body.name)
    if not name:
        raise unprocessable("Give the occasion a name.")
    o = Occasion(name=name, kind=_check_kind(body.kind or "christmas"), occasion_date=body.date, created_by_id=user.id)
    db.add(o)
    db.flush()

    sources: dict[int, Recipient] = {}
    if body.copy_from_id is not None:
        src_occ = load_occasion(db, user, body.copy_from_id)
        for r in db.scalars(
            select(Recipient).where(Recipient.occasion_id == src_occ.id, Recipient.owner_id == user.id)
        ).all():
            sources.setdefault(r.person_id, r)

    ids = list(dict.fromkeys(body.person_ids))
    people = {p.id: p for p in db.scalars(select(Person).where(Person.id.in_(ids), Person.owner_id == user.id))}
    if len(people) != len(ids):
        raise unprocessable("You can only add your own people.")
    if any(p.kind == PERSON_ME for p in people.values()):
        raise unprocessable("Add your own wishes from your wish list rather than as someone you buy for.")
    for pid in ids:
        db.add(_copy_entry(sources.get(pid), o, people[pid], body))
    if body.include_me or body.wish_ids:
        ensure_me(db, user)
        wishes = db.scalars(select(Wish).where(Wish.id.in_(body.wish_ids), Wish.owner_id == user.id)).all()
        if len(wishes) != len(set(body.wish_ids)):
            raise unprocessable("Some of those wishes aren't yours or no longer exist.")
        for w in wishes:
            w.occasion_id = o.id
    db.commit()
    db.refresh(o)
    return {"occasion": occasion_out(o, user)}


# --------------------------------------------------------------------------- one occasion


@router.get("/{occasion_id}/overview")
def overview(occasion_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    o = load_occasion(db, user, occasion_id)
    m = margin(db)
    entries = _visible_entries(db, user, o.id)
    categories = db.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()

    groups: dict[int | None, dict] = {
        c.id: {"category": {"id": c.id, "name": c.name}, "totals": Totals(), "recipients": []} for c in categories
    }
    groups[None] = {"category": None, "totals": Totals(), "recipients": []}
    occasion_totals = Totals()
    to_order, awaiting, reorder = [], [], []

    for r in entries:
        rt = Totals(budget=r.budget_pence).add_gifts(r.gifts)
        cat = r.person.category_id
        g = groups[cat if cat in groups else None]
        g["recipients"].append(recipient_out(r, user, m))
        g["totals"].merge(rt)
        occasion_totals.merge(rt)
        for gift in r.gifts:
            row = {**gift_out(gift), "recipient_name": r.name}
            if gift.status == STATUS_IDEA:
                to_order.append(row)
            elif gift.status == STATUS_ORDERED:
                awaiting.append(row)
            elif gift.status == STATUS_REORDER:
                reorder.append(row)

    to_order.sort(key=lambda x: (x["priority"], x["recipient_name"].lower(), x["id"]))
    awaiting.sort(key=lambda x: (x["delivery_date"] or "9999-12-31", x["recipient_name"].lower(), x["id"]))

    out = {
        "occasion": occasion_out(o, user),
        "read_only": o.is_archived,
        "margin_pence": m,
        "totals": occasion_totals.to_dict(m),
        "groups": [{**g, "totals": g["totals"].to_dict(m)} for g in groups.values() if g["recipients"]],
        "to_order": to_order,
        "awaiting_delivery": awaiting,
        "needs_reorder": sorted(reorder, key=lambda x: (x["recipient_name"].lower(), x["id"])),
        "my_wishes": occasion_wishes(db, user, o.id),
    }
    if can_manage(o, user):
        # What a delete would remove, including entries other people added that you can't see.
        out["delete_impact"] = {
            "recipients": db.scalar(select(func.count()).where(Recipient.occasion_id == o.id)) or 0,
            "gifts": db.scalar(select(func.count(Gift.id)).join(Recipient).where(Recipient.occasion_id == o.id)) or 0,
            # Your wishes here move to Anytime; nobody else's are revealed.
            "my_wishes": db.scalar(select(func.count()).where(Wish.occasion_id == o.id, Wish.owner_id == user.id)) or 0,
        }
    return out


@router.patch("/{occasion_id}")
def update_occasion(
    occasion_id: int, body: OccasionIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    o = load_occasion(db, user, occasion_id)
    _manage(o, user)
    fields = body.model_fields_set
    if "name" in fields:
        name = clean(body.name)
        if not name:
            raise unprocessable("Give the occasion a name.")
        o.name = name
    if "kind" in fields:
        o.kind = _check_kind(body.kind)
    if "date" in fields:
        o.occasion_date = body.date
    db.commit()
    return {"occasion": occasion_out(o, user)}


@router.post("/{occasion_id}/archive")
def archive(occasion_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    o = load_occasion(db, user, occasion_id)
    _manage(o, user)
    if not o.is_archived:
        o.is_archived = True
        o.archived_at = datetime.now(UTC)
        db.commit()
    return {"occasion": occasion_out(o, user)}


@router.post("/{occasion_id}/unarchive")
def unarchive(occasion_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    o = load_occasion(db, user, occasion_id)
    _manage(o, user)
    o.is_archived = False
    o.archived_at = None
    db.commit()
    return {"occasion": occasion_out(o, user)}


@router.delete("/{occasion_id}")
def delete_occasion(occasion_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Deletes the occasion with its entries and gifts. People are kept."""
    o = load_occasion(db, user, occasion_id)
    _manage(o, user)
    db.delete(o)
    db.commit()
    return {"ok": True}


@router.post("/{occasion_id}/recipients", status_code=201)
def add_recipient(
    occasion_id: int, body: EntryIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    o = load_occasion(db, user, occasion_id, write=True)
    if body.person_id is not None:
        person = db.get(Person, body.person_id)
        if person is None or person.owner_id != user.id:
            raise HTTPException(404, "Person not found.")
        if person.kind == PERSON_ME:
            raise unprocessable("Add your own wishes from your wish list rather than as someone you buy for.")
        if any(e.occasion_id == o.id for e in person.entries):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{person.name} is already in {o.name}.")
    else:
        person = Person(owner_id=user.id, name="")
        db.add(person)
        apply_person_fields(db, person, body, {"name", "notes", "category_id"})
    r = Recipient(occasion_id=o.id, owner_id=user.id, person=person, budget_pence=body.budget_pence)
    r.mirror_person()
    db.add(r)
    db.flush()
    if body.share_user_ids:
        set_shares(db, r, body.share_user_ids)
    db.commit()
    db.refresh(r)
    return {"recipient": recipient_out(r, user, margin(db))}
