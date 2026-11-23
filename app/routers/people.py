"""Your people: linked across occasions and private to you."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..common import occasion_out
from ..db import get_db
from ..models import Person, User
from ..security import current_user
from .lists import apply_person_fields

router = APIRouter(prefix="/api/people", tags=["people"])


class PersonIn(BaseModel):
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
    return {"people": [person_out(p, user) for p in people]}


@router.post("", status_code=201)
def create_person(body: PersonIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = Person(owner_id=user.id, name="")
    db.add(p)
    apply_person_fields(db, p, body, {"name", "notes", "category_id"})
    db.commit()
    db.refresh(p)
    return {"person": person_out(p, user)}


@router.patch("/{person_id}")
def update_person(person_id: int, body: PersonIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _mine(db, user, person_id)
    apply_person_fields(db, p, body, set(body.model_fields_set))
    db.commit()
    db.refresh(p)
    return {"person": person_out(p, user)}


@router.delete("/{person_id}")
def delete_person(person_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = _mine(db, user, person_id)
    if p.entries:
        names = ", ".join(sorted({e.occasion.name for e in p.entries}))
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{p.name} is still in: {names}. Remove them from those occasions first."
        )
    db.delete(p)
    db.commit()
    return {"ok": True}
