"""add owner to projects

Revision ID: 50c399f2985d
Revises: 9a1519c83396
Create Date: 2026-09-08 15:00:49.861200

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "50c399f2985d"
down_revision: str | Sequence[str] | None = "9a1519c83396"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("projects", sa.Column("owner_id", sa.Integer(), nullable=False))
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_foreign_key(None, "projects", "users", ["owner_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, "projects", type_="foreignkey")
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_column("projects", "owner_id")
