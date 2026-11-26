"""Turns the documentation pages into searchable chunks, and searches them.

Each Markdown page is split into chunks by heading, every chunk is embedded by an
OpenAI-compatible embeddings API, and the chunks are stored in `doc_chunks`. A
search embeds the question the same way and merges the nearest chunks with the
best full-text matches.

Only public documentation goes through here, never user data.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx2
from fastapi import Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from manta.config.chat_config import (
    chat_embed_api_key,
    chat_embed_base_url,
    chat_embed_model,
    get_chat_http_client,
)
from manta.config.database_config import get_db_session
from manta.entities import DocChunk
from manta.entities.doc_chunk import EMBEDDING_DIMENSIONS
from manta.services.results.doc_ingest_result import DocSearchHit, IngestDocsResult

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 1800
"""About 500 tokens. A code block or table longer than this stays whole."""

_EMBED_BATCH_SIZE = 16
# Each ranked list contributes this many candidates to the fusion.
_CANDIDATES = 20
# The usual constant of reciprocal-rank fusion: it keeps one list's top hit from
# outweighing a chunk that both lists rank well.
_RRF_K = 60

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# A heading's own anchor, as in `## Title {#my-anchor}` (the attr_list extension).
_HEADING_ID = re.compile(r"\s*\{\s*#([\w-]+)[^}]*\}\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LEADING_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


@dataclass(frozen=True)
class Chunk:
    heading_path: str
    """The headings above the chunk, outermost first, joined with ` > `."""

    anchor: str
    """The anchor of the nearest heading, as the docs site generates it."""

    content: str
    """The heading path followed by the text, so the chunk reads on its own."""


class EmbeddingError(Exception):
    """The embeddings API failed or returned vectors of an unexpected size."""


def _slugify(heading: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")


def _blocks(lines: list[str]) -> list[str]:
    """Splits a section into blocks at blank lines. A fenced code block is one
    block even with blank lines inside, and a table has none, so neither is split."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _pack(blocks: list[str], max_chars: int) -> list[str]:
    """Joins blocks into texts of at most `max_chars`, never cutting a block."""
    texts: list[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) + 2 > max_chars:
            texts.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current:
        texts.append(current)
    return texts


def chunk_markdown(markdown: str, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """Splits a page into chunks: one per heading section, and more when a section
    is longer than `max_chars`. A section without text gives no chunk."""
    markdown = markdown.replace("\r\n", "\n")
    markdown = _FRONT_MATTER.sub("", _LEADING_COMMENT.sub("", markdown, count=1), count=1)

    chunks: list[Chunk] = []
    # Level, title and anchor of each heading above the current section.
    headings: list[tuple[int, str, str]] = []
    section: list[str] = []

    def close_section() -> None:
        path = " > ".join(title for _, title, _ in headings)
        anchor = headings[-1][2] if headings else ""
        for body in _pack(_blocks(section), max_chars):
            chunks.append(Chunk(path, anchor, f"{path}\n\n{body}" if path else body))
        section.clear()

    in_fence = False
    for line in markdown.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.match(line)
        if heading is None:
            section.append(line)
            continue
        close_section()
        level = len(heading.group(1))
        while headings and headings[-1][0] >= level:
            headings.pop()
        title = heading.group(2)
        own_id = _HEADING_ID.search(title)
        if own_id:
            title = title[: own_id.start()]
        headings.append((level, title, own_id.group(1) if own_id else _slugify(title)))
    close_section()
    return chunks


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


_SEARCH_SQL = text(
    """
    WITH vector_hits AS (
        SELECT id, row_number() OVER (ORDER BY embedding <=> CAST(:embedding AS vector)) AS rank
        FROM doc_chunks
        WHERE embedding_model = :model
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :candidates
    ),
    -- plainto_tsquery joins the words with AND, which a whole question rarely
    -- satisfies. OR lets any of its words match, and ts_rank_cd orders the hits.
    question AS (
        SELECT CAST(
            replace(CAST(plainto_tsquery('english', :question) AS text), '&', '|') AS tsquery
        ) AS query
    ),
    text_hits AS (
        SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, query) DESC) AS rank
        FROM doc_chunks, question
        WHERE embedding_model = :model AND tsv @@ query
        ORDER BY ts_rank_cd(tsv, query) DESC
        LIMIT :candidates
    )
    SELECT c.doc_path, c.heading_path, c.url, c.content,
           coalesce(1.0 / (:rrf_k + v.rank), 0) + coalesce(1.0 / (:rrf_k + t.rank), 0) AS score,
           v.rank AS vector_rank, t.rank AS text_rank
    FROM doc_chunks c
    LEFT JOIN vector_hits v ON v.id = c.id
    LEFT JOIN text_hits t ON t.id = c.id
    WHERE v.id IS NOT NULL OR t.id IS NOT NULL
    ORDER BY score DESC, c.id
    LIMIT :top_k
    """
)


class DocIngestService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        client: httpx2.Client = Depends(get_chat_http_client),
        base_url: str = Depends(chat_embed_base_url),
        model: str = Depends(chat_embed_model),
        api_key: str | None = Depends(chat_embed_api_key),
    ) -> None:
        self.db = db
        self.client = client
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in the same order."""
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[start : start + _EMBED_BATCH_SIZE]
            try:
                response = self.client.post(
                    f"{self.base_url}/embeddings",
                    json={"model": self.model, "input": batch},
                    headers=headers,
                )
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
            except (httpx2.HTTPError, KeyError, ValueError) as error:
                raise EmbeddingError(f"Embedding with {self.model} failed: {error}") from error
            if len(data) != len(batch):
                raise EmbeddingError(f"Asked for {len(batch)} embeddings, got {len(data)}.")
            for item in data:
                if len(item["embedding"]) != EMBEDDING_DIMENSIONS:
                    raise EmbeddingError(
                        f"{self.model} returned {len(item['embedding'])} dimensions, "
                        f"the doc_chunks table stores {EMBEDDING_DIMENSIONS}."
                    )
                vectors.append(item["embedding"])
        return vectors

    def ingest(self, docs_dir: Path, sections: list[str], force: bool = False) -> IngestDocsResult:
        """Brings `doc_chunks` in line with the Markdown pages of `sections`.

        A page whose text and embedding model are unchanged is skipped, unless
        `force` is set, which a change to the chunking needs. Each page is replaced
        in its own transaction, so a search never sees half a page."""
        pages = {
            path.relative_to(docs_dir).as_posix(): path
            for section in sections
            for path in sorted((docs_dir / section).rglob("*.md"))
        }
        stored = {
            doc_path: (content_hash, model)
            for doc_path, content_hash, model in self.db.query(
                DocChunk.doc_path, DocChunk.content_hash, DocChunk.embedding_model
            ).distinct()
        }

        embedded_docs = unchanged_docs = removed_docs = embedded_chunks = 0
        for doc_path in stored.keys() - pages.keys():
            self.db.query(DocChunk).filter(DocChunk.doc_path == doc_path).delete()
            self.db.commit()
            removed_docs += 1

        for doc_path, path in pages.items():
            markdown = path.read_text(encoding="utf-8")
            content_hash = hashlib.sha256(markdown.encode()).hexdigest()
            if not force and stored.get(doc_path) == (content_hash, self.model):
                unchanged_docs += 1
                continue

            chunks = chunk_markdown(markdown)
            # Embedded before the delete, so a failing API leaves the old chunks in place.
            vectors = self.embed([chunk.content for chunk in chunks]) if chunks else []
            self.db.query(DocChunk).filter(DocChunk.doc_path == doc_path).delete()
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                self.db.add(
                    DocChunk(
                        doc_path=doc_path,
                        chunk_index=index,
                        heading_path=chunk.heading_path,
                        url=f"{doc_path}#{chunk.anchor}" if chunk.anchor else doc_path,
                        kind=doc_path.split("/", 1)[0],
                        content=chunk.content,
                        content_hash=content_hash,
                        embedding_model=self.model,
                        embedding=vector,
                    )
                )
            self.db.commit()
            if chunks:
                embedded_docs += 1
                embedded_chunks += len(chunks)
            elif doc_path in stored:
                removed_docs += 1
            logger.info("Embedded %s (%d chunks)", doc_path, len(chunks))

        return IngestDocsResult(
            embedded_docs=embedded_docs,
            unchanged_docs=unchanged_docs,
            removed_docs=removed_docs,
            embedded_chunks=embedded_chunks,
            total_chunks=self.db.query(func.count(DocChunk.id)).scalar() or 0,
        )

    def search(self, question: str, top_k: int) -> list[DocSearchHit]:
        """The `top_k` chunks that best match the question, by embedding distance
        and full-text match merged with reciprocal-rank fusion."""
        embedding = self.embed([question])[0]
        rows = self.db.execute(
            _SEARCH_SQL,
            {
                "embedding": _vector_literal(embedding),
                "model": self.model,
                "question": question,
                "candidates": _CANDIDATES,
                "rrf_k": _RRF_K,
                "top_k": top_k,
            },
        )
        return [DocSearchHit.model_validate(dict(row._mapping)) for row in rows]
