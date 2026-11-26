"""Command line for the chat's docs index: `manta-ingest-docs`.

uv run manta-ingest-docs ingest            # embed new and changed pages
uv run manta-ingest-docs ingest --force    # embed every page again
uv run manta-ingest-docs search "How do I start a run?"
"""

import argparse
import sys
import time

import httpx2
from sqlalchemy.orm import Session

from manta.config.chat_config import (
    chat_docs_dir,
    chat_docs_sections,
    chat_embed_api_key,
    chat_embed_base_url,
    chat_embed_model,
    chat_rag_top_k,
)
from manta.config.database_config import get_engine
from manta.services.doc_ingest_service import DocIngestService, EmbeddingError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manta-ingest-docs", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="chunk, embed and store the documentation pages")
    ingest.add_argument("--force", action="store_true", help="embed unchanged pages too")
    search = commands.add_parser("search", help="show the chunks that best match a question")
    search.add_argument("question")
    search.add_argument("-k", "--top-k", type=int, default=None)
    return parser


def main() -> None:
    args = _parser().parse_args()
    # A first request loads the model into memory, which is slow on a CPU.
    with Session(get_engine()) as db, httpx2.Client(timeout=300) as client:
        service = DocIngestService(
            db, client, chat_embed_base_url(), chat_embed_model(), chat_embed_api_key()
        )
        started = time.perf_counter()
        try:
            if args.command == "ingest":
                result = service.ingest(chat_docs_dir(), chat_docs_sections(), force=args.force)
                print(
                    f"Embedded {result.embedded_chunks} chunks from {result.embedded_docs} pages, "
                    f"{result.unchanged_docs} pages unchanged, {result.removed_docs} removed. "
                    f"{result.total_chunks} chunks stored. "
                    f"Took {time.perf_counter() - started:.1f} s."
                )
                return
            hits = service.search(args.question, args.top_k or chat_rag_top_k())
        except EmbeddingError as error:
            sys.exit(str(error))

        print(f"{len(hits)} hits in {time.perf_counter() - started:.1f} s\n")
        for position, hit in enumerate(hits, start=1):
            preview = " ".join(hit.content.split("\n\n", 1)[-1].split())[:160]
            print(
                f"{position}. {hit.url}\n"
                f"   {hit.heading_path}\n"
                f"   score {hit.score:.4f}, vector rank {hit.vector_rank}, "
                f"text rank {hit.text_rank}\n"
                f"   {preview}\n"
            )


if __name__ == "__main__":
    main()
