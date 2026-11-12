"""add updated_at to projects, runs and users

Revision ID: b3d7a1c25e90
Revises: f9c434bf905f
Create Date: 2026-11-06 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d7a1c25e90"
down_revision: str | Sequence[str] | None = "f9c434bf905f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("projects", "runs", "users")


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        # Added nullable first so existing rows can be backfilled before NOT NULL applies.
        op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        # A row never updated has `updated_at == created_at`; `now()` would invent a change.
        table_clause = sa.table(table, sa.column("updated_at"), sa.column("created_at"))
        op.execute(table_clause.update().values(updated_at=table_clause.c.created_at))
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in TABLES:
        op.drop_column(table, "updated_at")
