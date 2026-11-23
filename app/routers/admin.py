"""Admin dashboard: invites, categories and app settings."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..common import all_settings, clean, set_setting, unprocessable
from ..config import settings
from ..db import get_db
from ..models import Category, Invite, User
from ..security import current_user, hash_token, require_admin

router = APIRouter(prefix="/api", tags=["admin"])


# --------------------------------------------------------------------------- invites


class InviteIn(BaseModel):
    note: str | None = Field(default=None, max_length=120)
    make_admin: bool = False
    days: int | None = Field(default=None, ge=1, le=90)


def _invite_out(i: Invite) -> dict:
    now = datetime.now(UTC)
    state = "used" if i.used_at else ("expired" if i.expires_at < now else "open")
    return {
        "id": i.id,
        "note": i.note,
        "make_admin": i.make_admin,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "expires_at": i.expires_at.isoformat(),
        "used_at": i.used_at.isoformat() if i.used_at else None,
        "used_by": i.used_by.name if i.used_by else None,
        "state": state,
    }


@router.get("/invites")
def list_invites(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    invites = db.scalars(select(Invite).order_by(Invite.created_at.desc())).all()
    return {"invites": [_invite_out(i) for i in invites]}


@router.post("/invites", status_code=201)
def create_invite(body: InviteIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    token = secrets.token_urlsafe(24)
    invite = Invite(
        token_hash=hash_token(token),
        note=clean(body.note),
        make_admin=body.make_admin,
        created_by_id=admin.id,
        expires_at=datetime.now(UTC) + timedelta(days=body.days or settings.invite_days),
    )
    db.add(invite)
    db.commit()
    # The raw token is returned once; the client builds the link from its own origin.
    return {"invite": _invite_out(invite), "token": token, "path": f"/#/invite/{token}"}


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(404, "Invite not found.")
    db.delete(invite)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- categories


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class CategoryOrderIn(BaseModel):
    ids: list[int]


def category_out(c: Category) -> dict:
    return {"id": c.id, "name": c.name, "sort_order": c.sort_order}


def _category_name(db: Session, name: str, exclude_id: int | None = None) -> str:
    name = clean(name)
    if not name:
        raise unprocessable("Give the category a name.")
    q = select(Category.id).where(func.lower(Category.name) == name.lower())
    if exclude_id is not None:
        q = q.where(Category.id != exclude_id)
    if db.scalar(q) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A category with that name already exists.")
    return name


@router.get("/categories")
def list_categories(_: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cats = db.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()
    return {"categories": [category_out(c) for c in cats]}


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    name = _category_name(db, body.name)
    last = db.scalar(select(func.max(Category.sort_order))) or 0
    cat = Category(name=name, sort_order=last + 1)
    db.add(cat)
    db.commit()
    return {"category": category_out(cat)}


@router.patch("/categories/{cat_id}")
def rename_category(
    cat_id: int, body: CategoryIn, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    cat = db.get(Category, cat_id)
    if cat is None:
        raise HTTPException(404, "Category not found.")
    cat.name = _category_name(db, body.name, exclude_id=cat.id)
    db.commit()
    return {"category": category_out(cat)}


@router.put("/categories/order")
def reorder_categories(body: CategoryOrderIn, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    cats = {c.id: c for c in db.scalars(select(Category)).all()}
    if set(body.ids) != set(cats):
        raise unprocessable("The order must list every category exactly once.")
    for i, cid in enumerate(body.ids):
        cats[cid].sort_order = i + 1
    db.commit()
    return list_categories(_, db)


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Recipients in the category become uncategorised."""
    cat = db.get(Category, cat_id)
    if cat is None:
        raise HTTPException(404, "Category not found.")
    db.delete(cat)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- settings


class SettingsIn(BaseModel):
    budget_margin_pence: int | None = Field(default=None, ge=0, le=100_000)


@router.get("/settings")
def get_settings(_: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"settings": all_settings(db)}


@router.put("/settings")
def update_settings(body: SettingsIn, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    for key, value in body.model_dump(exclude_none=True).items():
        set_setting(db, key, value)
    db.commit()
    return {"settings": all_settings(db)}
