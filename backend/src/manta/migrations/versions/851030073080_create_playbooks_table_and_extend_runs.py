"""create playbooks table and extend runs

Revision ID: 851030073080
Revises: 851030073079
Create Date: 2026-09-16 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "851030073080"
down_revision: str | Sequence[str] | None = "851030073079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Built-in playbooks are seeded with fixed UUIDs so every environment agrees on them.
CLUSTER_EXPAND_DISPATCH_UUID = "0f0b7a9e-3f43-4bf0-9f0e-6c1f8a2d4e01"

# The example playbook that ships with manta-batteries
# (manta-batteries/src/manta_batteries/examples/cluster_expand_dispatch.yaml),
# inlined so the migration is self-contained.
#
# TODO: replace seeding-by-migration with a deploy-time sync of built-in playbooks
# from the pinned manta-batteries version, once playbooks are more than this PoC.
CLUSTER_EXPAND_DISPATCH_DOC = {
    "name": "cluster-expand-dispatch",
    "initial_data": {"dims": ["snapshot"]},
    "steps": [
        {"name": "cluster", "block": "cluster_time"},
        {
            "name": "expansion_overnight",
            "block": "overnight_capacity_expansion",
            "when": {"config": "globals.expansion_mode", "equals": "overnight"},
        },
        {
            "name": "expansion_myopic",
            "block": "myopic_capacity_expansion",
            "when": {"config": "globals.expansion_mode", "equals": "myopic"},
        },
        {
            "name": "dispatch",
            "block": "rolling_horizon_dispatch",
            "when": {"config": "globals.expansion_mode", "equals": "overnight"},
            "inputs": {"capacity_source": "${steps.expansion_overnight.output}"},
        },
    ],
}

CLUSTER_EXPAND_DISPATCH_CONFIG = {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 168, "overlap": 24}},
}


def upgrade() -> None:
    playbooks = op.create_table(
        "playbooks",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("doc", JSONB(), nullable=False),
        sa.Column("default_config", JSONB(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("uuid"),
    )

    op.add_column("runs", sa.Column("playbook_id", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("playbook_config", JSONB(), nullable=True))
    op.add_column("runs", sa.Column("input_key", sa.Text(), nullable=True))
    op.create_foreign_key("runs_playbook_id_fkey", "runs", "playbooks", ["playbook_id"], ["id"])

    op.bulk_insert(
        playbooks,
        [
            {
                "uuid": CLUSTER_EXPAND_DISPATCH_UUID,
                "name": "cluster-expand-dispatch",
                "description": (
                    "Cluster a network's time series, expand its capacity (overnight "
                    "or myopically), then dispatch against the chosen capacities."
                ),
                "doc": CLUSTER_EXPAND_DISPATCH_DOC,
                "default_config": CLUSTER_EXPAND_DISPATCH_CONFIG,
            }
        ],
    )


def downgrade() -> None:
    op.drop_constraint("runs_playbook_id_fkey", "runs", type_="foreignkey")
    op.drop_column("runs", "input_key")
    op.drop_column("runs", "playbook_config")
    op.drop_column("runs", "playbook_id")
    op.drop_table("playbooks")
