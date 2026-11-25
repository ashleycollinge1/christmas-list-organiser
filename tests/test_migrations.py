"""Production safety: upgrading a database must keep every row and value.

Seeds a database at each released schema with realistic data, upgrades to head
and compares. Add a case here for every future migration.
"""

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command

TABLES_V010 = ["users", "invites", "categories", "seasons", "recipients", "recipient_shares", "gifts", "app_settings"]


def _cfg():
    cfg = Config("alembic.ini")
    cfg.attributes["configure_logger"] = False
    return cfg


def _snapshot(conn, tables, columns=None):
    """Every row of every table as dicts, keyed by table (only the given columns if set)."""
    out = {}
    for t in tables:
        cols = "*" if not columns or t not in columns else ", ".join(columns[t])
        out[t] = [dict(r._mapping) for r in conn.execute(text(f"SELECT {cols} FROM {t} ORDER BY 1, 2"))]
    return out


V010_COLUMNS = {
    "users": ["id", "username", "password_hash", "role", "is_active", "must_change_password", "created_at"],
    "seasons": ["id", "name", "is_archived", "created_at", "archived_at"],
    "recipients": ["id", "season_id", "owner_id", "name", "budget_pence", "notes", "category_id", "created_at"],
}

SEED_V010 = """
INSERT INTO users (id, username, display_name, password_hash, role, is_active, must_change_password)
  VALUES (1, 'admin', 'Ashley', 'hash-a', 'admin', true, false),
         (2, 'sam', 'Sam', 'hash-s', 'user', true, false);
INSERT INTO invites (token_hash, note, make_admin, created_by_id, expires_at)
  VALUES ('t1', 'For Jo', false, 1, now() + interval '7 days');
INSERT INTO categories (id, name, sort_order) VALUES (1, 'Kids', 1), (2, 'Family', 2);
INSERT INTO app_settings (key, value) VALUES ('budget_margin_pence', '700');
INSERT INTO seasons (id, name, is_archived, archived_at) VALUES
  (1, 'Christmas 2025', true, now()), (2, 'Christmas 2026', false, NULL);
INSERT INTO recipients (id, season_id, owner_id, name, budget_pence, notes, category_id) VALUES
  (1, 1, 1, 'Molly', 25000, 'Size 7-8', 1),      -- Molly 2025
  (2, 2, 1, 'molly ', 30000, 'Size 7-8', 1),     -- same person in 2026 (same notes) -> merged
  (3, 2, 1, 'Dad', NULL, NULL, NULL),
  (4, 1, 1, 'Dad', 5000, 'Likes whisky', 2),     -- blanks on one side -> merged, blanks filled
  (5, 2, 1, 'Jo', 4000, 'Vegan', NULL),
  (6, 1, 1, 'Jo', 3000, 'Allergic to nuts', NULL), -- conflicting notes -> stays separate
  (7, 2, 2, 'Molly', 2000, 'From Sam', NULL);    -- other owner -> separate person
INSERT INTO recipient_shares (recipient_id, user_id) VALUES (2, 2);
INSERT INTO gifts (recipient_id, description, link, price_pence, quantity, my_share_pence, priority, status,
                   notes, buyer_id, retailer, tracking_number, delivery_date, hiding_place)
  VALUES (2, 'Lego', 'https://example.com/lego', 4999, 1, NULL, 1, 'ordered', 'Gift receipt', 1, 'Argos',
          'TRK1', '2026-12-04', 'Loft'),
         (2, 'Paint', NULL, 1250, 2, 1000, 2, 'wrapped', NULL, 2, NULL, NULL, NULL, 'Wardrobe'),
         (1, 'Old gift', NULL, 1000, 1, NULL, 3, 'given', NULL, 1, NULL, NULL, NULL, NULL);
SELECT setval('users_id_seq', 2); SELECT setval('categories_id_seq', 2);
SELECT setval('seasons_id_seq', 2); SELECT setval('recipients_id_seq', 7);
"""


@pytest.fixture()
def v010_db(migrated):
    """Database at the v0.1.0 schema (0001) with seed data; restored to head afterwards."""
    from app.db import engine

    _reset_schema(engine)
    command.upgrade(_cfg(), "0001")
    with engine.begin() as c:
        c.execute(text(SEED_V010))
    yield engine
    _reset_schema(engine)
    command.upgrade(_cfg(), "head")


def _reset_schema(engine):
    engine.dispose()
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()


def test_upgrade_0001_to_head_preserves_everything(v010_db):
    with v010_db.connect() as c:
        before = _snapshot(c, TABLES_V010)

    command.upgrade(_cfg(), "head")

    with v010_db.connect() as c:
        after = _snapshot(c, TABLES_V010)
        # Every original row and column value is unchanged (new columns aside).
        for table, rows in before.items():
            assert len(after[table]) == len(rows), table
            for old, new in zip(rows, after[table], strict=True):
                for col, val in old.items():
                    assert new[col] == val, f"{table}.{col} changed: {val!r} -> {new[col]!r}"

        seasons = c.execute(text("SELECT id, kind, created_by_id FROM seasons ORDER BY id")).all()
        assert [(s.kind, s.created_by_id) for s in seasons] == [("christmas", 1), ("christmas", 1)]

        links = dict(c.execute(text("SELECT id, person_id FROM recipients")).all())
        assert None not in links.values()
        people = {p.id: p for p in c.execute(text("SELECT id, owner_id, name, notes, category_id FROM people")).all()}
        # Molly 2025 + 2026 merged (identical notes); Dad merged with blanks filled.
        assert links[1] == links[2]
        assert links[3] == links[4]
        dad = people[links[3]]
        assert (dad.notes, dad.category_id) == ("Likes whisky", 2)
        # Jo has conflicting notes: two people, both notes kept.
        assert links[5] != links[6]
        assert {people[links[5]].notes, people[links[6]].notes} == {"Vegan", "Allergic to nuts"}
        # Sam's Molly is Sam's own person.
        assert people[links[7]].owner_id == 2 and links[7] != links[1]
        assert len(people) == 5

        # Two active occasions are now allowed.
        c.execute(text("INSERT INTO seasons (name, is_archived) VALUES ('Molly birthday', false)"))
        c.rollback()


def test_upgraded_data_works_through_the_api(v010_db):
    """After upgrading, the app serves the old data correctly."""
    command.upgrade(_cfg(), "head")
    from fastapi.testclient import TestClient

    from app.db import engine
    from app.main import app
    from app.security import hash_password, login_limiter

    with engine.begin() as c:
        c.execute(text("UPDATE users SET password_hash = :h"), {"h": hash_password("correct-horse-battery")})
    login_limiter.reset()
    from tests.conftest import Api

    api = Api(TestClient(app))
    assert api.login().status_code == 200
    occasions = api.get("/api/occasions").json()["occasions"]
    assert [(o["name"], o["is_archived"]) for o in occasions] == [("Christmas 2026", False), ("Christmas 2025", True)]
    o = api.get("/api/occasions/2/overview").json()
    assert o["margin_pence"] == 700
    names = sorted(r["name"] for g in o["groups"] for r in g["recipients"])
    # The merged person is named after their earliest entry; the 2026 row's own value is kept in the DB.
    assert names == ["Dad", "Jo", "Molly"]
    molly = next(r for g in o["groups"] for r in g["recipients"] if r["name"] == "Molly")
    assert molly["totals"]["spent_pence"] == 4999 + 1000
    assert molly["notes"] == "Size 7-8" and molly["category"]["name"] == "Kids"


def test_downgrade_refuses_with_several_active(v010_db):
    command.upgrade(_cfg(), "head")
    with v010_db.begin() as c:
        c.execute(text("INSERT INTO seasons (name, is_archived) VALUES ('Second', false)"))
    with pytest.raises(RuntimeError, match="active"):
        command.downgrade(_cfg(), "0001")


TABLES_V020 = TABLES_V010 + ["people"]


def test_upgrade_0002_to_head_preserves_everything(v010_db):
    """v0.2.0 -> v0.3.0: every row and value at 0002 is unchanged; people become 'recipient'."""
    command.upgrade(_cfg(), "0002")
    with v010_db.begin() as c:
        # Some v0.2.0-era data on top: a birthday occasion with a dated, non-Christmas kind.
        c.execute(text("INSERT INTO seasons (name, kind, occasion_date, is_archived, created_by_id) "
                       "VALUES ('Molly birthday', 'birthday', '2027-03-14', false, 1)"))  # fmt: skip
    with v010_db.connect() as c:
        before = _snapshot(c, TABLES_V020)

    command.upgrade(_cfg(), "head")

    with v010_db.connect() as c:
        after = _snapshot(c, TABLES_V020)
        for table, rows in before.items():
            assert len(after[table]) == len(rows), table
            for old, new in zip(rows, after[table], strict=True):
                for col, val in old.items():
                    assert new[col] == val, f"{table}.{col} changed: {val!r} -> {new[col]!r}"
        assert {r["kind"] for r in after["people"]} == {"recipient"}
        assert c.execute(text("SELECT count(*) FROM wishes")).scalar_one() == 0


def test_downgrade_0003_refuses_when_wishes_exist(v010_db):
    command.upgrade(_cfg(), "head")
    with v010_db.begin() as c:
        c.execute(text("INSERT INTO people (owner_id, kind, name) VALUES (1, 'me', 'Ashley')"))
        c.execute(text("INSERT INTO wishes (owner_id, person_id, description, quantity, priority) "
                       "SELECT 1, id, 'Book', 1, 2 FROM people WHERE kind = 'me'"))  # fmt: skip
    with pytest.raises(RuntimeError, match="wishes"):
        command.downgrade(_cfg(), "0002")


def test_upgrade_0003_to_head_keeps_gifts_and_allows_reorder(v010_db):
    command.upgrade(_cfg(), "0003")
    with v010_db.connect() as c:
        before = _snapshot(c, ["gifts"])
    command.upgrade(_cfg(), "head")
    with v010_db.begin() as c:
        assert _snapshot(c, ["gifts"]) == before
        c.execute(text("UPDATE gifts SET status = 'reorder' WHERE id = (SELECT min(id) FROM gifts)"))
    with pytest.raises(RuntimeError, match="reorder"):
        command.downgrade(_cfg(), "0003")
