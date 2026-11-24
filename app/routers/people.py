"""Your people: linked across occasions and private to you."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..common import occasion_out
from ..db import get_db
from ..models import PERSON_KINDS, PERSON_ME, PERSON_RECIPIENT, Person, User, Wish
from ..security import current_user
from .lists import apply_person_fields

router = APIRouter(prefix="/api/people", tags=["people"])


class PersonIn(BaseModel):
    kind: str | None = None  # only on create: "recipient" (default) or "me"
    name: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=4000)
    category_id: int | None = None


def person_out(p: Person, user: User) -> dict:
    entries = sorted(
        p.entries,
        key=lambda e: (e.occasion.is_archived, -(e.occasion.created_at.timestamp() if e.occasion.created_at else 0)),
    )
    return {
        "id": p.id,
        "kind": p.kind,
        "name": p.name,
        "notes": p.notes,
        "category": {"id": p.category.id, "name": p.category.name} if p.category else None,
        "entries": [
            {"recipient_id": e.id, "budget_pence": e.budget_pence, "occasion": occasion_out(e.occasion, user)}
            for e in entries
        ],
    }


def _mine(db: Session, user: User, person_id: int) -> Person:
    p = db.get(Person, person_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Person not found.")
    return p


@router.get("")
def list_people(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    people = db.scalars(select(Person).where(Person.owner_id == user.id).order_by(func.lower(Person.name))).all()
    # "Me" first, then everyone else alphabetically.
    people = sorted(people, key=lambda p: not p.is_me)
    return {"people": [person_out(p, user) for p in people]}


@router.post("", status_code=201)
def create_person(body: PersonIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    kind = body.kind or PERSON_RECIPIENT
    if kind not in PERSON_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Type must be 'recipient' or 'me'.")
    if kind == PERSON_ME and db.scalar(select(Person.id).where(Person.owner_id == user.id, Person.kind == PERSON_ME)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a 'Me' person.")
    p = Person(owner_id=user.id, kind=kind, name="")
    db.add(p)
    apply_person_fields(db, p, body, {"name", "notes"} if kind == PERSON_ME else {"name", "notes", "category_id"})
    db.commit()
    db.refresh(p)
    return {"person": person_out(p, user)}


@router.patch("/{person_id}")
def update_person(person_id: int, body: PersonIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _mine(db, user, person_id)
    if "kind" in body.model_fields_set and body.kind != p.kind:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A person's type can't be changed.")
    apply_person_fields(db, p, body, set(body.model_fields_set) - {"kind"})
    db.commit()
    db.refresh(p)
    return {"person": person_out(p, user)}


@router.delete("/{person_id}")
def delete_person(person_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = _mine(db, user, person_id)
    wishes = db.scalar(select(func.count()).where(Wish.person_id == p.id)) or 0
    if wishes:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"You have {wishes} wishes. Delete them before deleting your wish list."
        )
    if p.entries:
        names = ", ".join(sorted({e.occasion.name for e in p.entries}))
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{p.name} is still in: {names}. Remove them from those occasions first."
        )
    db.delete(p)
    db.commit()
    return {"ok": True}
