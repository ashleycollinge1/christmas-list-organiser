"""Admin dashboard: invites, categories, seasons and app settings."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..common import active_season, all_settings, clean, season_out, set_setting, unprocessable
from ..config import settings
from ..db import get_db
from ..models import (
    STATUS_IDEA,
    Category,
    Gift,
    Invite,
    Recipient,
    RecipientShare,
    Season,
    User,
)
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


# --------------------------------------------------------------------------- seasons


class SeasonCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    copy_recipients: bool = True
    copy_gifts: bool = False


class SeasonPatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("/seasons")
def list_seasons(_: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    seasons = db.scalars(select(Season).order_by(Season.is_archived, Season.created_at.desc())).all()
    return {"seasons": [season_out(s) for s in seasons]}


def _copy_season(db: Session, source: Season, target: Season, copy_gifts: bool) -> None:
    for r in db.scalars(select(Recipient).where(Recipient.season_id == source.id).order_by(Recipient.id)).all():
        nr = Recipient(
            season_id=target.id,
            owner_id=r.owner_id,
            name=r.name,
            budget_pence=r.budget_pence,
            notes=r.notes,
            category_id=r.category_id,
        )
        nr.shares = [RecipientShare(user_id=s.user_id) for s in r.shares]
        if copy_gifts:
            # Order details belong to last year; the idea itself carries over.
            nr.gifts = [
                Gift(
                    description=g.description,
                    link=g.link,
                    price_pence=g.price_pence,
                    quantity=g.quantity,
                    my_share_pence=g.my_share_pence,
                    priority=g.priority,
                    status=STATUS_IDEA,
                    notes=g.notes,
                    buyer_id=g.buyer_id,
                    retailer=g.retailer,
                )
                for g in r.gifts
            ]
        db.add(nr)


@router.post("/seasons", status_code=201)
def start_season(body: SeasonCreateIn, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Archive the current season and start a new one, optionally copying it over."""
    name = clean(body.name)
    if not name:
        raise unprocessable("Give the season a name.")
    previous = db.scalar(select(Season).where(Season.is_archived.is_(False)).with_for_update())
    if previous is not None:
        previous.is_archived = True
        previous.archived_at = datetime.now(UTC)
        db.flush()
    season = Season(name=name)
    db.add(season)
    db.flush()
    if previous is not None and body.copy_recipients:
        _copy_season(db, previous, season, body.copy_gifts)
    db.commit()
    return {"season": season_out(season)}


@router.patch("/seasons/{season_id}")
def rename_season(
    season_id: int, body: SeasonPatchIn, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found.")
    name = clean(body.name)
    if not name:
        raise unprocessable("Give the season a name.")
    season.name = name
    db.commit()
    return {"season": season_out(season)}


@router.post("/seasons/{season_id}/activate")
def reactivate_season(season_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    """Make an archived season active again (archiving the current one)."""
    season = db.get(Season, season_id)
    if season is None:
        raise HTTPException(404, "Season not found.")
    if not season.is_archived:
        return {"season": season_out(season)}
    current = active_season(db)
    if current is not None:
        current.is_archived = True
        current.archived_at = datetime.now(UTC)
        db.flush()
    season.is_archived = False
    season.archived_at = None
    db.commit()
    return {"season": season_out(season)}


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
