import os

import pytest

# Configure before the app is imported.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://xmas:xmas@localhost:55433/xmas")
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "correct-horse-battery"
os.environ["COOKIE_SECURE"] = "false"


def _db_available() -> bool:
    from sqlalchemy import create_engine, text

    try:
        with create_engine(os.environ["DATABASE_URL"]).connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def migrated():
    if not _db_available():
        pytest.skip("PostgreSQL not available (set DATABASE_URL)")
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    cfg.attributes["configure_logger"] = False
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def client(migrated):
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db import engine
    from app.main import app
    from app.security import login_limiter

    with engine.begin() as c:
        c.execute(
            text(
                "TRUNCATE users, sessions, invites, app_settings, categories, seasons, people, wishes, "
                "recipients, recipient_shares, gifts RESTART IDENTITY CASCADE"
            )
        )
    login_limiter.reset()
    with TestClient(app) as tc:
        yield tc


class Api:
    """Small helper that tracks the CSRF token like the browser client does."""

    def __init__(self, client):
        self.c = client
        self.csrf = None

    def login(self, username="admin", password="correct-horse-battery"):
        r = self.c.post("/api/auth/login", json={"username": username, "password": password})
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]
        return r

    def _h(self):
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers={**self._h(), **kw.pop("headers", {})}, **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self._h(), **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self._h(), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(), **kw)


@pytest.fixture()
def api(client):
    a = Api(client)
    assert a.login().status_code == 200
    return a


def make_user(api, username, password="another-good-password"):
    """Create a user as admin and return a logged-in Api for them (password already changed)."""
    r = api.post("/api/users", json={"username": username})
    assert r.status_code == 201, r.text
    temp = r.json()["temporary_password"]
    from fastapi.testclient import TestClient

    other = Api(TestClient(api.c.app))
    assert other.login(username, temp).status_code == 200
    r = other.post("/api/auth/password", json={"current_password": temp, "new_password": password})
    assert r.status_code == 200, r.text
    return other


@pytest.fixture()
def second(api):
    """A second, non-admin user with their own cookie jar."""
    return make_user(api, "sam")
