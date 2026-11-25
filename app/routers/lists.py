"""Recipients (a person's entry in an occasion), gifts, and the shared access rules.

Visibility: a recipient is visible only to its owner and the users it is shared
with. An occasion is visible to its creator and to anyone who can see a
recipient in it. Admins get no special access, so "hidden from" holds for
everyone. Archived occasions are read-only.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from ..budget import Totals, gift_cost, line_total
from ..common import clean, clean_link, margin, occasion_out, unprocessable
from ..db import get_db
from ..models import (
    PRIORITY_MEDIUM,
    STATUS_IDEA,
    STATUSES,
    Category,
    Gift,
    Occasion,
    Person,
    Recipient,
    RecipientShare,
    User,
)
from ..security import current_user

router = APIRouter(prefix="/api", tags=["lists"])

MAX_PENCE = 10_000_000  # GBP 100,000
STATUS_RANK = {s: i for i, s in enumerate(STATUSES)}


# --------------------------------------------------------------------------- access


def visible_recipient(user: User):
    shared = select(RecipientShare.recipient_id).where(RecipientShare.user_id == user.id)
    return or_(Recipient.owner_id == user.id, Recipient.id.in_(shared))


def visible_occasion(user: User):
    has_visible = exists().where(Recipient.occasion_id == Occasion.id, visible_recipient(user))
    return or_(Occasion.created_by_id == user.id, has_visible)


def load_occasion(db: Session, user: User, occasion_id: int, *, write: bool = False) -> Occasion:
    o = db.scalar(select(Occasion).where(Occasion.id == occasion_id, visible_occasion(user)))
    if o is None:
        raise HTTPException(404, "Occasion not found.")
    if write:
        writable(o)
    return o


def writable(o: Occasion) -> None:
    if o.is_archived:
        raise HTTPException(status.HTTP_409_CONFLICT, "This occasion is archived and read-only. Unarchive it to edit.")


def load_recipient(db: Session, user: User, recipient_id: int, *, write: bool = False) -> Recipient:
    r = db.scalar(select(Recipient).where(Recipient.id == recipient_id, visible_recipient(user)))
    if r is None:
        raise HTTPException(404, "Recipient not found.")
    if write:
        writable(r.occasion)
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


def recipient_out(r: Recipient, user: User, m: int, read_only: bool | None = None, with_gifts: bool = True) -> dict:
    totals = Totals(budget=r.budget_pence).add_gifts(r.gifts)
    p = r.person
    out = {
        "id": r.id,
        "person_id": p.id,
        "occasion_id": r.occasion_id,
        "occasion": {"id": r.occasion.id, "name": r.occasion.name, "kind": r.occasion.kind},
        "name": p.name,
        "budget_pence": r.budget_pence,
        "notes": p.notes,
        "category": {"id": p.category.id, "name": p.category.name} if p.category else None,
        "owner": _person(r.owner),
        "is_owner": r.owner_id == user.id,
        "shared_with": sorted((_person(s.user) for s in r.shares), key=lambda p: p["name"].lower()),
        "read_only": r.occasion.is_archived if read_only is None else read_only,
        "totals": totals.to_dict(m),
    }
    if with_gifts:
        out["gifts"] = [gift_out(g) for g in sorted_gifts(r.gifts)]
    return out


# --------------------------------------------------------------------------- recipients


class RecipientIn(BaseModel):
    # Person fields (owner only): changing them updates every occasion the person is in.
    name: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=4000)
    category_id: int | None = None
    # Entry fields.
    budget_pence: int | None = Field(default=None, ge=0, le=MAX_PENCE)


class SharesIn(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=50)


PERSON_FIELDS = {"name", "notes", "category_id"}


def check_category(db: Session, category_id: int | None) -> None:
    if category_id is not None and db.get(Category, category_id) is None:
        raise unprocessable("That category no longer exists.")


def apply_person_fields(db: Session, p: Person, body: BaseModel, fields: set[str]) -> None:
    if "name" in fields:
        name = clean(body.name)
        if not name:
            raise unprocessable("Give them a name.")
        p.name = name
    if "notes" in fields:
        p.notes = clean(body.notes)
    if "category_id" in fields:
        check_category(db, body.category_id)
        p.category_id = body.category_id
    db.flush()
    db.refresh(p)
    for entry in p.entries:
        entry.mirror_person()


def set_shares(db: Session, r: Recipient, user_ids: list[int]) -> None:
    ids = set(user_ids) - {r.owner_id}
    if ids:
        found = set(db.scalars(select(User.id).where(User.id.in_(ids), User.is_active.is_(True))).all())
        if found != ids:
            raise unprocessable("Some of those people don't exist or are deactivated.")
    current = {s.user_id: s for s in r.shares}
    for uid in set(current) - ids:
        r.shares.remove(current[uid])
    for uid in ids - set(current):
        r.shares.append(RecipientShare(user_id=uid))


@router.get("/recipients/{recipient_id}")
def get_recipient(recipient_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    r = load_recipient(db, user, recipient_id)
    return {"recipient": recipient_out(r, user, margin(db)), "occasion": occasion_out(r.occasion, user)}


@router.patch("/recipients/{recipient_id}")
def update_recipient(
    recipient_id: int, body: RecipientIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    r = load_recipient(db, user, recipient_id, write=True)
    fields = body.model_fields_set
    if fields & PERSON_FIELDS:
        if r.owner_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who added them can change their details.")
        apply_person_fields(db, r.person, body, fields & PERSON_FIELDS)
    if "budget_pence" in fields:
        r.budget_pence = body.budget_pence
    db.commit()
    db.refresh(r)
    return {"recipient": recipient_out(r, user, margin(db))}


@router.delete("/recipients/{recipient_id}")
def remove_recipient(recipient_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Remove someone from an occasion (with their gifts there). The person is kept."""
    r = load_recipient(db, user, recipient_id, write=True)
    if r.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who added them can remove them.")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.put("/recipients/{recipient_id}/shares")
def update_shares(
    recipient_id: int, body: SharesIn, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    r = load_recipient(db, user, recipient_id, write=True)
    if r.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who added them can change sharing.")
    set_shares(db, r, body.user_ids)
    db.commit()
    db.refresh(r)
    return {"recipient": recipient_out(r, user, margin(db))}


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
    return {"gift": gift_out(g), "recipient": recipient_out(r, user, margin(db), with_gifts=False)}


@router.patch("/gifts/{gift_id}")
def update_gift(gift_id: int, body: GiftIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = load_gift(db, user, gift_id, write=True)
    r = g.recipient
    _apply_gift(g, body, r, set(body.model_fields_set))
    db.commit()
    db.refresh(g)
    db.refresh(r)
    return {"gift": gift_out(g), "recipient": recipient_out(r, user, margin(db), with_gifts=False)}


@router.delete("/gifts/{gift_id}")
def delete_gift(gift_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    g = load_gift(db, user, gift_id, write=True)
    r = g.recipient
    db.delete(g)
    db.commit()
    db.refresh(r)
    return {"ok": True, "recipient": recipient_out(r, user, margin(db), with_gifts=False)}


# --------------------------------------------------------------------------- bulk


class GiftBulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(status|move|delete)$")
    status: str | None = None
    occasion_id: int | None = None  # move: the same person's entry in this occasion


def _target_entry(db: Session, user: User, source: Recipient, occasion_id: int) -> Recipient:
    """The same person's entry in another occasion, created if they aren't in it yet (owner only)."""
    target_occ = load_occasion(db, user, occasion_id, write=True)
    entry = db.scalar(
        select(Recipient).where(Recipient.occasion_id == target_occ.id, Recipient.person_id == source.person_id)
    )
    if entry is not None:
        if db.scalar(select(Recipient.id).where(Recipient.id == entry.id, visible_recipient(user))) is None:
            raise HTTPException(404, "Recipient not found.")
        return entry
    if source.owner_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"{source.name} isn't in {target_occ.name}, and only their owner can add them."
        )
    entry = Recipient(occasion_id=target_occ.id, owner_id=user.id, person=source.person)
    entry.mirror_person()
    db.add(entry)
    db.flush()
    return entry


@router.post("/gifts/bulk")
def bulk_gifts(body: GiftBulkIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Apply one action to several gifts, all or nothing."""
    gifts = [load_gift(db, user, gid, write=True) for gid in dict.fromkeys(body.ids)]
    if body.action == "status":
        if body.status not in STATUSES:
            raise unprocessable(f"Status must be one of: {', '.join(STATUSES)}.")
        for g in gifts:
            g.status = body.status
    elif body.action == "move":
        if body.occasion_id is None:
            raise unprocessable("Choose where to move them.")
        for g in gifts:
            if g.recipient.occasion_id == body.occasion_id:
                continue
            target = _target_entry(db, user, g.recipient, body.occasion_id)
            g.recipient_id = target.id
            if g.buyer_id is not None and g.buyer_id not in _member_ids(target):
                g.buyer_id = user.id
    else:
        for g in gifts:
            db.delete(g)
    db.commit()
    return {"ok": True, "count": len(gifts)}
