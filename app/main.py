from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from .common import bootstrap_first_occasion
from .config import settings
from .db import SessionLocal
from .models import ROLE_ADMIN, User
from .routers import admin, auth, lists, occasions, people, users
from .security import hash_password

log = logging.getLogger("xmas")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def bootstrap_admin() -> None:
    """Create the initial admin from ADMIN_USERNAME/ADMIN_PASSWORD on first start only.

    An existing account is never modified, so changing the env later does nothing.
    That is deliberate: the env password is a bootstrap secret, not a source of truth.
    """
    with SessionLocal() as db:
        if db.scalar(select(func.count()).where(User.role == ROLE_ADMIN)):
            return
        if db.scalar(select(User).where(func.lower(User.username) == settings.admin_username.lower())):
            log.warning("User %r exists but there is no admin; not modifying it.", settings.admin_username)
            return
        if not settings.admin_password:
            raise RuntimeError("No administrator exists yet: set ADMIN_PASSWORD to create one on first start.")
        if len(settings.admin_password) < settings.min_password_length:
            raise RuntimeError(f"ADMIN_PASSWORD must be at least {settings.min_password_length} characters.")
        db.add(
            User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role=ROLE_ADMIN,
            )
        )
        db.commit()
        log.warning("Created initial administrator %r.", settings.admin_username)


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_admin()
    with SessionLocal() as db:
        bootstrap_first_occasion(db)
    yield


app = FastAPI(
    title="Christmas List Organiser",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    path = request.url.path
    if path == "/api/docs":
        # Swagger UI loads assets from a CDN; relax CSP only for the docs page.
        h["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com"
        )
    else:
        h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")
    elif path.startswith("/static/"):
        # Revalidate (cheap 304s) so iOS Safari never runs stale JS after an upgrade.
        h.setdefault("Cache-Control", "no-cache")
    return response


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(occasions.router)
app.include_router(people.router)
app.include_router(lists.router)


@app.get("/healthz", include_in_schema=False)
def healthz():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"ok": False}, status_code=503)
    return {"ok": True, "version": settings.app_version}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(path: str):
    return JSONResponse({"detail": "Not found."}, status_code=404)


app.mount("/static", StaticFiles(directory=settings.frontend_dir), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    # Hash-based routing means every non-API, non-static path serves the shell.
    return FileResponse(settings.frontend_dir / "index.html", headers={"Cache-Control": "no-cache"})
