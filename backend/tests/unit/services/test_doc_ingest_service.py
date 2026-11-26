import json
from unittest.mock import MagicMock

import httpx2
import pytest

from manta.entities.doc_chunk import EMBEDDING_DIMENSIONS
from manta.services.doc_ingest_service import (
    DocIngestService,
    EmbeddingError,
    chunk_markdown,
)

BASE_URL = "http://models.test/v1"

PAGE = """<!--
SPDX-FileCopyrightText: Manta contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Runs

A run executes a playbook.

## Start a run

Open the project and press Run.

### From the command line

```bash
# not a heading
manta run start

--project demo
```

## Empty section

## Results

| Column | Meaning |
| --- | --- |
| status | The run's state |
"""


def _service(handler, api_key: str | None = None) -> DocIngestService:
    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return DocIngestService(MagicMock(), client, BASE_URL, "bge-m3", api_key)


def _embeddings(request: httpx2.Request) -> httpx2.Response:
    texts = json.loads(request.content)["input"]
    data = [
        {"index": index, "embedding": [float(len(text))] * EMBEDDING_DIMENSIONS}
        for index, text in enumerate(texts)
    ]
    # Reversed on purpose: the API's `index` decides the order, not the position.
    return httpx2.Response(200, json={"data": data[::-1]})


def test_chunk_markdown_makes_one_chunk_per_section_with_text() -> None:
    chunks = chunk_markdown(PAGE)

    assert [chunk.heading_path for chunk in chunks] == [
        "Runs",
        "Runs > Start a run",
        "Runs > Start a run > From the command line",
        "Runs > Results",
    ]
    assert [chunk.anchor for chunk in chunks] == [
        "runs",
        "start-a-run",
        "from-the-command-line",
        "results",
    ]


def test_chunk_markdown_drops_the_licence_comment_and_prefixes_the_heading_path() -> None:
    first = chunk_markdown(PAGE)[0]

    assert "SPDX" not in first.content
    assert first.content == "Runs\n\nA run executes a playbook."


def test_chunk_markdown_keeps_a_code_block_whole_and_ignores_headings_inside_it() -> None:
    # Small enough that every blank-line-separated block would be its own chunk.
    chunks = chunk_markdown(PAGE, max_chars=20)

    code = [chunk for chunk in chunks if "```bash" in chunk.content]
    assert len(code) == 1
    assert "# not a heading\nmanta run start\n\n--project demo\n```" in code[0].content


def test_chunk_markdown_keeps_a_table_whole() -> None:
    chunks = chunk_markdown(PAGE, max_chars=20)

    table = [chunk for chunk in chunks if "| Column |" in chunk.content]
    assert len(table) == 1
    assert "| status | The run's state |" in table[0].content


def test_chunk_markdown_splits_a_long_section_at_blank_lines() -> None:
    page = "# Title\n\n" + "\n\n".join(f"Paragraph {n} " + "x" * 80 for n in range(6))

    chunks = chunk_markdown(page, max_chars=250)

    assert len(chunks) == 3
    assert all(chunk.heading_path == "Title" for chunk in chunks)
    assert all(len(chunk.content) <= 250 + len("Title\n\n") for chunk in chunks)


def test_chunk_markdown_strips_front_matter_and_handles_a_page_without_headings() -> None:
    chunks = chunk_markdown("---\ntitle: x\n---\nJust text.\r\nSecond line.")

    assert len(chunks) == 1
    assert chunks[0].heading_path == ""
    assert chunks[0].content == "Just text.\nSecond line."


def test_chunk_markdown_uses_a_headings_own_anchor() -> None:
    chunks = chunk_markdown("# Open questions\n\n### Who names a record? {#who-owns-a-record}\n\nx")

    assert chunks[0].heading_path == "Open questions > Who names a record?"
    assert chunks[0].anchor == "who-owns-a-record"


def test_embed_returns_vectors_in_input_order_across_batches() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return _embeddings(request)

    texts = ["x" * length for length in range(1, 21)]

    vectors = _service(handler).embed(texts)

    assert [vector[0] for vector in vectors] == [float(n) for n in range(1, 21)]
    assert len(requests) == 2
    assert str(requests[0].url) == f"{BASE_URL}/embeddings"
    assert json.loads(requests[0].content)["model"] == "bge-m3"


def test_embed_sends_the_api_key_only_when_one_is_set() -> None:
    seen: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers.get("Authorization"))
        return _embeddings(request)

    _service(handler).embed(["a"])
    _service(handler, api_key="secret").embed(["a"])

    assert seen == [None, "Bearer secret"]


def test_embed_rejects_a_vector_of_the_wrong_size() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    with pytest.raises(EmbeddingError, match="2 dimensions"):
        _service(handler).embed(["a"])


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx2.Response(500, text="model crashed"),
        lambda request: httpx2.Response(200, json={"unexpected": True}),
        lambda request: (_ for _ in ()).throw(httpx2.ConnectError("refused")),
    ],
    ids=["server-error", "malformed-body", "unreachable"],
)
def test_embed_turns_an_api_failure_into_an_embedding_error(handler) -> None:
    with pytest.raises(EmbeddingError, match="bge-m3"):
        _service(handler).embed(["a"])
