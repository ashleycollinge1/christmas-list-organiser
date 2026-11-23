"""occasions and linked people

Additive only. Nothing is dropped or renamed and no existing value is changed:

- seasons gains kind (existing rows become 'christmas'), occasion_date and
  created_by_id (existing rows: the first admin, who created them in v0.1.0).
- The "one active season" unique index is removed so several occasions can be
  active at once. It's an index, not data.
- New people table. Every recipient is linked to a person. Recipients with the
  same owner and name are merged into one person only when nothing conflicts
  (notes and category equal, or blank on one side); otherwise they stay separate.
- recipients.name / notes / category_id are kept untouched.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _compatible(a, b) -> bool:
    if _blank(a) or _blank(b):
        return True
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


def _link_people(bind) -> None:
    rows = bind.execute(
        sa.text("SELECT id, owner_id, name, notes, category_id, created_at FROM recipients ORDER BY id")
    ).all()
    people: dict[tuple[int, str], list[dict]] = {}
    for r in rows:
        key = (r.owner_id, r.name.strip().lower())
        match = next(
            (
                p
                for p in people.get(key, [])
                if _compatible(p["notes"], r.notes) and _compatible(p["category_id"], r.category_id)
            ),
            None,
        )
        if match is None:
            pid = bind.execute(
                sa.text(
                    "INSERT INTO people (owner_id, name, notes, category_id, created_at) "
                    "VALUES (:owner, :name, :notes, :cat, :created) RETURNING id"
                ),
                {"owner": r.owner_id, "name": r.name, "notes": r.notes, "cat": r.category_id, "created": r.created_at},
            ).scalar_one()
            people.setdefault(key, []).append({"id": pid, "notes": r.notes, "category_id": r.category_id})
        else:
            pid = match["id"]
            # Fill blanks on the merged person from this entry; never overwrite.
            if _blank(match["notes"]) and not _blank(r.notes):
                bind.execute(sa.text("UPDATE people SET notes = :n WHERE id = :id"), {"n": r.notes, "id": pid})
                match["notes"] = r.notes
            if match["category_id"] is None and r.category_id is not None:
                bind.execute(
                    sa.text("UPDATE people SET category_id = :c WHERE id = :id"), {"c": r.category_id, "id": pid}
                )
                match["category_id"] = r.category_id
        bind.execute(sa.text("UPDATE recipients SET person_id = :pid WHERE id = :id"), {"pid": pid, "id": r.id})


def upgrade() -> None:
    # 1. Occasions: kind, date and creator.
    op.add_column("seasons", sa.Column("kind", sa.String(length=16), server_default="christmas", nullable=False))
    op.add_column("seasons", sa.Column("occasion_date", sa.Date(), nullable=True))
    op.add_column("seasons", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "seasons_created_by_id_fkey", "seasons", "users", ["created_by_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_seasons_created_by_id", "seasons", ["created_by_id"], unique=False)
    op.create_check_constraint("ck_seasons_kind", "seasons", "kind IN ('christmas','birthday','other')")
    op.execute(
        "UPDATE seasons SET created_by_id = "
        "(SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1) WHERE created_by_id IS NULL"
    )

    # 2. Allow several active occasions.
    op.drop_index("uq_seasons_one_active", table_name="seasons", postgresql_where=sa.text("NOT is_archived"))

    # 3. Linked people.
    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_people_owner_id", "people", ["owner_id"], unique=False)

    # 4. Link every recipient to a person.
    op.add_column("recipients", sa.Column("person_id", sa.Integer(), nullable=True))
    _link_people(op.get_bind())
    op.alter_column("recipients", "person_id", nullable=False)
    op.create_foreign_key("recipients_person_id_fkey", "recipients", "people", ["person_id"], ["id"])
    op.create_index("ix_recipients_person_id", "recipients", ["person_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    active = bind.execute(sa.text("SELECT count(*) FROM seasons WHERE NOT is_archived")).scalar_one()
    if active > 1:
        raise RuntimeError(
            f"{active} occasions are active; v0.1.0 allows one. Archive all but one before downgrading, "
            "or restore the backup taken before upgrading."
        )
    op.drop_index("ix_recipients_person_id", table_name="recipients")
    op.drop_constraint("recipients_person_id_fkey", "recipients", type_="foreignkey")
    op.drop_column("recipients", "person_id")
    op.drop_index("ix_people_owner_id", table_name="people")
    op.drop_table("people")
    op.create_index(
        "uq_seasons_one_active", "seasons", ["is_archived"], unique=True, postgresql_where=sa.text("NOT is_archived")
    )
    op.drop_constraint("ck_seasons_kind", "seasons", type_="check")
    op.drop_index("ix_seasons_created_by_id", table_name="seasons")
    op.drop_constraint("seasons_created_by_id_fkey", "seasons", type_="foreignkey")
    op.drop_column("seasons", "created_by_id")
    op.drop_column("seasons", "occasion_date")
    op.drop_column("seasons", "kind")
