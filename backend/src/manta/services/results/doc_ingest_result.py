from pydantic import BaseModel


class IngestDocsResult(BaseModel):
    embedded_docs: int
    """Pages that were new or changed, and so were chunked and embedded."""

    unchanged_docs: int
    removed_docs: int
    """Pages whose chunks were deleted because the file is gone or now empty."""

    embedded_chunks: int
    total_chunks: int
    """Chunks in the table after the run."""


class DocSearchHit(BaseModel):
    doc_path: str
    heading_path: str
    url: str
    content: str
    score: float
    """Reciprocal-rank fusion of the two ranks below; higher is better."""

    vector_rank: int | None
    """Rank by embedding distance, None when the chunk was only a full-text hit."""

    text_rank: int | None
    """Rank by full-text match, None when the chunk was only an embedding hit."""
