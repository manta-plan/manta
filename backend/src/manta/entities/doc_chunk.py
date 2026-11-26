from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from manta.entities.base import Base

EMBEDDING_DIMENSIONS = 1024
"""The vector size of bge-m3. A model with another size needs a migration, not
only a re-embed, because the column type carries the size."""


class DocChunk(Base):
    """One section of a public documentation page, with its embedding.

    Holds documentation only, never user data."""

    __tablename__ = "doc_chunks"
    __table_args__ = (
        UniqueConstraint("doc_path", "chunk_index"),
        Index(
            "ix_doc_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_doc_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    # Path of the page below the docs folder, e.g. `user-guide/concepts.md`.
    doc_path: Mapped[str] = mapped_column(index=True)
    chunk_index: Mapped[int]
    # The headings above the chunk, e.g. `Concepts > Project`, shown in citations.
    heading_path: Mapped[str]
    # `doc_path` plus the heading's anchor, so a citation points at a section.
    url: Mapped[str]
    # The docs section the page is in (`user-guide`, `explanation`, ...).
    kind: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    # Hash of the whole page: an unchanged page is not embedded again.
    content_hash: Mapped[str]
    # Vectors of two models cannot be compared, so a model change re-embeds the page.
    embedding_model: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    # Full-text half of the hybrid search: exact terms such as `p_nom_opt` match
    # better lexically than by embedding.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
