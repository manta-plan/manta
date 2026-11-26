"""create doc_chunks table

Revision ID: c4e8f2a91b37
Revises: b3d7a1c25e90
Create Date: 2026-11-25 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4e8f2a91b37"
down_revision: str | Sequence[str] | None = "b3d7a1c25e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Needs the pgvector/pgvector Postgres image: plain postgres has no `vector`.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # The chat's only table: public documentation, chunked and embedded. Chat
    # messages are not stored on the server at all, so there is no table for them.
    op.create_table(
        "doc_chunks",
        sa.Column("doc_path", sa.String(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_path", "chunk_index"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("ix_doc_chunks_doc_path", "doc_chunks", ["doc_path"])
    op.create_index(
        "ix_doc_chunks_embedding",
        "doc_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_doc_chunks_tsv", "doc_chunks", ["tsv"], postgresql_using="gin")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("doc_chunks")
    # The `vector` extension stays: dropping it would fail for any other user of it.
