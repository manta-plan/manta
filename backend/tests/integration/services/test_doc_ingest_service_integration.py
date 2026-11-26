import json
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from manta.entities import DocChunk
from manta.entities.doc_chunk import EMBEDDING_DIMENSIONS
from manta.services.doc_ingest_service import DocIngestService

BACKEND_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

# Each topic owns one dimension, so a text about it is nearest to a question about it.
TOPICS = ("solver", "keycloak", "bucket")


def _fake_embeddings(request: httpx2.Request) -> httpx2.Response:
    data = []
    for index, text in enumerate(json.loads(request.content)["input"]):
        vector = [0.0] * EMBEDDING_DIMENSIONS
        vector[-1] = 0.01  # never a zero vector, which has no cosine distance
        for dimension, topic in enumerate(TOPICS):
            vector[dimension] = float(text.lower().count(topic))
        data.append({"index": index, "embedding": vector})
    return httpx2.Response(200, json={"data": data})


@pytest.fixture
def embed_calls() -> list[int]:
    """The number of texts in each call to the fake embeddings API."""
    return []


@pytest.fixture
def service(
    app_server: str, postgres_service: dict[str, str], embed_calls: list[int]
) -> Iterator[DocIngestService]:
    """A service on the test database, which the app has migrated on startup,
    with a fake embeddings API. Leaves `doc_chunks` empty."""
    env = dotenv_values(BACKEND_ENV_FILE)
    engine = create_engine(
        f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{postgres_service['host']}:{postgres_service['port']}/{env['POSTGRES_DB']}"
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        embed_calls.append(len(json.loads(request.content)["input"]))
        return _fake_embeddings(request)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    with Session(engine) as db:
        db.query(DocChunk).delete()
        db.commit()
        yield DocIngestService(db, client, "http://models.test/v1", "fake-model")
        db.rollback()
        db.query(DocChunk).delete()
        db.commit()
    engine.dispose()


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    (tmp_path / "user-guide").mkdir()
    (tmp_path / "contributing").mkdir()
    (tmp_path / "user-guide" / "runs.md").write_text(
        "# Runs\n\nA run can fail when the solver times out.\n\n"
        "## Storage\n\nResults are written to the bucket.\n",
        encoding="utf-8",
    )
    (tmp_path / "user-guide" / "login.md").write_text(
        "# Login\n\nUsers sign in through Keycloak.\n", encoding="utf-8"
    )
    (tmp_path / "contributing" / "tests.md").write_text(
        "# Tests\n\nThe solver has unit tests.\n", encoding="utf-8"
    )
    return tmp_path


def test_ingest_stores_the_chunks_of_the_chosen_sections(
    service: DocIngestService, docs_dir: Path
) -> None:
    # When
    result = service.ingest(docs_dir, ["user-guide"])

    # Then
    assert (result.embedded_docs, result.embedded_chunks, result.total_chunks) == (2, 3, 3)
    stored = service.db.query(DocChunk).order_by(DocChunk.doc_path, DocChunk.chunk_index).all()
    assert [(chunk.doc_path, chunk.heading_path, chunk.url, chunk.kind) for chunk in stored] == [
        ("user-guide/login.md", "Login", "user-guide/login.md#login", "user-guide"),
        ("user-guide/runs.md", "Runs", "user-guide/runs.md#runs", "user-guide"),
        ("user-guide/runs.md", "Runs > Storage", "user-guide/runs.md#storage", "user-guide"),
    ]
    assert all(chunk.embedding_model == "fake-model" for chunk in stored)
    assert all(len(chunk.embedding) == EMBEDDING_DIMENSIONS for chunk in stored)


def test_ingest_embeds_only_what_changed(
    service: DocIngestService, docs_dir: Path, embed_calls: list[int]
) -> None:
    # Given
    service.ingest(docs_dir, ["user-guide"])
    embed_calls.clear()

    # When nothing changed
    unchanged = service.ingest(docs_dir, ["user-guide"])

    # Then
    assert (unchanged.embedded_docs, unchanged.unchanged_docs) == (0, 2)
    assert embed_calls == []

    # When one page changes and the other is deleted
    (docs_dir / "user-guide" / "login.md").write_text(
        "# Login\n\nUsers sign in through Keycloak.\n\n## Logout\n\nPress Sign out.\n",
        encoding="utf-8",
    )
    (docs_dir / "user-guide" / "runs.md").unlink()
    changed = service.ingest(docs_dir, ["user-guide"])

    # Then
    assert (changed.embedded_docs, changed.removed_docs, changed.total_chunks) == (1, 1, 2)
    assert embed_calls == [2]
    assert {chunk.doc_path for chunk in service.db.query(DocChunk)} == {"user-guide/login.md"}


def test_ingest_embeds_again_when_forced_or_when_the_model_changes(
    service: DocIngestService, docs_dir: Path, embed_calls: list[int]
) -> None:
    # Given
    service.ingest(docs_dir, ["user-guide"])

    # When
    forced = service.ingest(docs_dir, ["user-guide"], force=True)
    service.model = "other-model"
    other_model = service.ingest(docs_dir, ["user-guide"])

    # Then
    assert forced.embedded_docs == 2
    assert other_model.embedded_docs == 2
    assert other_model.total_chunks == 3
    assert {chunk.embedding_model for chunk in service.db.query(DocChunk)} == {"other-model"}


def test_search_ranks_the_matching_chunk_first(service: DocIngestService, docs_dir: Path) -> None:
    # Given
    service.ingest(docs_dir, ["user-guide"])

    # When
    hits = service.search("Why did the solver stop?", top_k=3)

    # Then
    assert hits[0].url == "user-guide/runs.md#runs"
    assert hits[0].vector_rank == 1
    assert hits[0].text_rank == 1
    assert hits[0].score > hits[1].score


def test_search_finds_a_chunk_by_an_exact_word_the_embedding_misses(
    service: DocIngestService, docs_dir: Path
) -> None:
    # Given: "written" is none of the fake embedding's topics, so only the
    # full-text half of the search can tell the chunks apart.
    service.ingest(docs_dir, ["user-guide"])

    # When
    hits = service.search("written", top_k=1)

    # Then
    assert hits[0].url == "user-guide/runs.md#storage"
    assert hits[0].text_rank == 1
