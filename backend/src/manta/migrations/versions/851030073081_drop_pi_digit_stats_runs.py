"""drop pi-digit-stats runs and require a playbook on every run

Revision ID: 851030073081
Revises: 851030073080
Create Date: 2026-09-21 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "851030073081"
down_revision: str | Sequence[str] | None = "851030073080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("playbook_name", "playbook_doc", "playbook_config", "input_url", "output_prefix")


def upgrade() -> None:
    """Upgrade schema."""
    # The pi-digit-stats demo workflow is gone, and with it the only kind of run
    # that had no playbook. Its rows cannot be shown or re-run, so they go rather
    # than keeping five columns nullable for them.
    op.execute(sa.text("DELETE FROM runs WHERE playbook_name IS NULL"))
    for column in _COLUMNS:
        op.alter_column("runs", column, nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    for column in _COLUMNS:
        op.alter_column("runs", column, nullable=True)
