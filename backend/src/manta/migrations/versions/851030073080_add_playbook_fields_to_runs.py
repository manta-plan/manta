"""add playbook fields to runs

Revision ID: 851030073080
Revises: 851030073079
Create Date: 2026-09-17 12:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "851030073080"
down_revision: str | Sequence[str] | None = "851030073079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("runs", sa.Column("playbook_name", sa.String(), nullable=True))
    op.add_column("runs", sa.Column("playbook_doc", JSONB(), nullable=True))
    op.add_column("runs", sa.Column("playbook_config", JSONB(), nullable=True))
    op.add_column("runs", sa.Column("input_url", sa.String(), nullable=True))
    op.add_column("runs", sa.Column("output_prefix", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "output_prefix")
    op.drop_column("runs", "input_url")
    op.drop_column("runs", "playbook_config")
    op.drop_column("runs", "playbook_doc")
    op.drop_column("runs", "playbook_name")
