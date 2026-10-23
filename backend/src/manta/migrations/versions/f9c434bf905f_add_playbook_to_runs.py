"""add playbook to runs

Revision ID: f9c434bf905f
Revises: 50c399f2985d
Create Date: 2026-10-01 12:07:54.375714

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9c434bf905f"
down_revision: str | Sequence[str] | None = "50c399f2985d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("runs", sa.Column("playbook", sa.String(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "playbook")
