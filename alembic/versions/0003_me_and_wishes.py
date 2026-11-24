"""me person and wish list

Additive only. Nothing is dropped or renamed and no existing value is changed:

- people gains kind; every existing person becomes 'recipient' (someone you buy for).
- A partial unique index allows at most one 'me' person per account. No existing
  row is 'me', so it can't conflict.
- New wishes table. A wish whose occasion is deleted falls back to Anytime
  (occasion_id SET NULL) instead of being deleted.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("people", sa.Column("kind", sa.String(length=16), server_default="recipient", nullable=False))
    op.create_check_constraint("ck_people_kind", "people", "kind IN ('recipient','me')")
    op.create_index("uq_people_one_me", "people", ["owner_id"], unique=True, postgresql_where=sa.text("kind = 'me'"))

    op.create_table(
        "wishes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("occasion_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("link", sa.String(length=2048), nullable=True),
        sa.Column("price_pence", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_wish_quantity"),
        sa.CheckConstraint("price_pence IS NULL OR price_pence >= 0", name="ck_wish_price"),
        sa.CheckConstraint("priority BETWEEN 1 AND 3", name="ck_wish_priority"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"]),
        sa.ForeignKeyConstraint(["occasion_id"], ["seasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wishes_owner_id", "wishes", ["owner_id"], unique=False)
    op.create_index("ix_wishes_person_id", "wishes", ["person_id"], unique=False)
    op.create_index("ix_wishes_occasion_id", "wishes", ["occasion_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    wishes = bind.execute(sa.text("SELECT count(*) FROM wishes")).scalar_one()
    mes = bind.execute(sa.text("SELECT count(*) FROM people WHERE kind = 'me'")).scalar_one()
    if wishes or mes:
        raise RuntimeError(
            f"There are {wishes} wishes and {mes} 'me' people; downgrading would delete them. "
            "Restore the backup taken before upgrading instead."
        )
    op.drop_index("ix_wishes_occasion_id", table_name="wishes")
    op.drop_index("ix_wishes_person_id", table_name="wishes")
    op.drop_index("ix_wishes_owner_id", table_name="wishes")
    op.drop_table("wishes")
    op.drop_index("uq_people_one_me", table_name="people", postgresql_where=sa.text("kind = 'me'"))
    op.drop_constraint("ck_people_kind", "people", type_="check")
    op.drop_column("people", "kind")
