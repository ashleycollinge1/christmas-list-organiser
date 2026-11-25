"""gift status: add 'reorder'

Only widens the allowed values of gifts.status; no data is touched.
The check constraint is replaced in one transaction, so it's never missing.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "status IN ('idea','ordered','delivered','wrapped','given')"
NEW = "status IN ('idea','ordered','delivered','wrapped','given','reorder')"


def upgrade() -> None:
    op.drop_constraint("ck_gift_status", "gifts", type_="check")
    op.create_check_constraint("ck_gift_status", "gifts", NEW)


def downgrade() -> None:
    n = op.get_bind().execute(sa.text("SELECT count(*) FROM gifts WHERE status = 'reorder'")).scalar_one()
    if n:
        raise RuntimeError(
            f"{n} gifts are in 'reorder'; downgrading can't store that. Change their status first, "
            "or restore the backup taken before upgrading."
        )
    op.drop_constraint("ck_gift_status", "gifts", type_="check")
    op.create_check_constraint("ck_gift_status", "gifts", OLD)
