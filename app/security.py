"""Password hashing, sessions, CSRF and login rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuthSession, User

SESSION_COOKIE = "xmas_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile: t=3, m=64 MiB, p=4).
_hasher = PasswordHasher()
# Used to equalise timing when a username does not exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


# --------------------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def burn_dummy_verify(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def validate_new_password(password: str, username: str | None = None) -> None:
    if len(password) < settings.min_password_length:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Password must be at least {settings.min_password_length} characters.",
        )
    if len(password) > 1024:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Password is too long.")
    if username and password.lower() == username.lower():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Password must not match the username.")


def generate_temp_password() -> str:
    # ~96 bits of entropy, URL/clipboard friendly.
    return secrets.token_urlsafe(12)


# --------------------------------------------------------------------------- sessions


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, response: Response) -> AuthSession:
    token = secrets.token_urlsafe(32)
    sess = AuthSession(
        token_hash=hash_token(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
    )
    db.add(sess)
    # Opportunistically clear expired sessions.
    db.execute(delete(AuthSession).where(AuthSession.expires_at < datetime.now(UTC)))
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return sess


def destroy_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")


def destroy_user_sessions(db: Session, user_id: int, keep_token_hash: str | None = None) -> None:
    stmt = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep_token_hash:
        stmt = stmt.where(AuthSession.token_hash != keep_token_hash)
    db.execute(stmt)


def load_session(db: Session, request: Request) -> AuthSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if sess is None:
        return None
    if sess.expires_at < datetime.now(UTC) or not sess.user.is_active:
        db.delete(sess)
        db.commit()
        return None
    return sess


# --------------------------------------------------------------------------- dependencies


def _check_csrf(request: Request, sess: AuthSession) -> None:
    if request.method in SAFE_METHODS:
        return
    sent = request.headers.get(CSRF_HEADER, "")
    if not sent or not hmac.compare_digest(sent, sess.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing CSRF token.")


def current_session(request: Request, db: Session = Depends(get_db)) -> AuthSession:
    """Authenticated session plus CSRF check, without the forced password-change gate."""
    sess = load_session(db, request)
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    _check_csrf(request, sess)
    request.state.session = sess
    return sess


def current_user(sess: AuthSession = Depends(current_session)) -> User:
    if sess.user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "password_change_required")
    return sess.user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required.")
    return user


# --------------------------------------------------------------------------- rate limiting


class LoginRateLimiter:
    """Sliding-window failure counter keyed by IP and by username.

    In-memory: correct for a single web process, which is how the image runs.
    """

    def __init__(self) -> None:
        self._fails: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._fails[key]
        while q and now - q[0] > settings.login_window_seconds:
            q.popleft()
        return q

    def retry_after(self, ip: str, username: str) -> int:
        now = time.monotonic()
        with self._lock:
            worst = 0
            for key in (f"ip:{ip}", f"user:{username.lower()}"):
                q = self._prune(key, now)
                # IPs get a larger allowance (shared NAT), usernames the configured limit.
                limit = settings.login_max_failures * (4 if key.startswith("ip:") else 1)
                if len(q) >= limit:
                    worst = max(worst, int(settings.login_window_seconds - (now - q[0])) + 1)
            return worst

    def fail(self, ip: str, username: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in (f"ip:{ip}", f"user:{username.lower()}"):
                self._prune(key, now).append(now)

    def succeed(self, username: str) -> None:
        with self._lock:
            self._fails.pop(f"user:{username.lower()}", None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()


login_limiter = LoginRateLimiter()
