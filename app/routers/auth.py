from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..common import clean
from ..config import settings
from ..db import get_db
from ..models import ROLE_ADMIN, ROLE_USER, AuthSession, Invite, User
from ..security import (
    burn_dummy_verify,
    create_session,
    current_session,
    destroy_session,
    destroy_user_sessions,
    hash_password,
    hash_token,
    load_session,
    login_limiter,
    needs_rehash,
    validate_new_password,
    verify_password,
)
from .users import USERNAME_RE, username_taken

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)


class InviteAcceptIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    display_name: str | None = Field(default=None, max_length=80)
    password: str = Field(min_length=1, max_length=1024)


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "name": user.name,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limit(ip: str, key: str) -> None:
    wait = login_limiter.retry_after(ip, key)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s).",
            headers={"Retry-After": str(wait)},
        )


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip = _client_ip(request)
    _rate_limit(ip, body.username)

    user = db.scalar(select(User).where(func.lower(User.username) == body.username.strip().lower()))
    if user is None:
        burn_dummy_verify(body.password)
        ok = False
    else:
        ok = verify_password(user.password_hash, body.password) and user.is_active

    if not ok:
        login_limiter.fail(ip, body.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password.")

    login_limiter.succeed(body.username)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    # Drop any pre-existing cookie session to prevent fixation.
    destroy_session(db, request, response)
    sess = create_session(db, user, response)
    return {"user": user_out(user), "csrf_token": sess.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    # CSRF-checked when a session exists; logging out without one is a no-op.
    sess = load_session(db, request)
    if sess is not None:
        current_session(request, db)
    destroy_session(db, request, response)
    return {"ok": True}


@router.get("/me")
def me(sess: AuthSession = Depends(current_session)) -> dict:
    return {"user": user_out(sess.user), "csrf_token": sess.csrf_token, "version": settings.app_version}


@router.patch("/me")
def update_profile(body: ProfileIn, sess: AuthSession = Depends(current_session), db: Session = Depends(get_db)):
    user = db.get(User, sess.user_id)
    user.display_name = clean(body.display_name)
    db.commit()
    return {"user": user_out(user)}


@router.post("/password")
def change_password(
    body: PasswordChangeIn,
    sess: AuthSession = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    user = db.get(User, sess.user_id)
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "New password must differ from the current one.")
    validate_new_password(body.new_password, user.username)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    # Sign out every other device.
    destroy_user_sessions(db, user.id, keep_token_hash=sess.token_hash)
    db.commit()
    return {"user": user_out(user)}


# --------------------------------------------------------------------------- invites


def _usable_invite(db: Session, token: str) -> Invite:
    invite = db.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
    if invite is None or invite.used_at is not None or invite.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite link is invalid, used or expired.")
    return invite


@router.get("/invite/{token}")
def check_invite(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = _client_ip(request)
    _rate_limit(ip, "invite")
    try:
        invite = _usable_invite(db, token)
    except HTTPException:
        login_limiter.fail(ip, "invite-probe")
        raise
    return {"ok": True, "expires_at": invite.expires_at.isoformat()}


@router.post("/invite/{token}")
def accept_invite(
    token: str, body: InviteAcceptIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> dict:
    ip = _client_ip(request)
    _rate_limit(ip, "invite")
    invite = db.scalar(select(Invite).where(Invite.token_hash == hash_token(token)).with_for_update())
    if invite is None or invite.used_at is not None or invite.expires_at < datetime.now(UTC):
        login_limiter.fail(ip, "invite-probe")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite link is invalid, used or expired.")
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Usernames use letters, numbers, dot, dash or underscore (2-64 characters).",
        )
    if username_taken(db, username):
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken.")
    validate_new_password(body.password, username)
    user = User(
        username=username,
        display_name=clean(body.display_name),
        password_hash=hash_password(body.password),
        role=ROLE_ADMIN if invite.make_admin else ROLE_USER,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    invite.used_at = datetime.now(UTC)
    invite.used_by_id = user.id
    destroy_session(db, request, response)
    sess = create_session(db, user, response)
    return {"user": user_out(user), "csrf_token": sess.csrf_token}
