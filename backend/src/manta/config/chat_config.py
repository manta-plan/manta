import os
import threading
from functools import lru_cache
from pathlib import Path

import httpx2
from dotenv import load_dotenv

_REPO_DOCS_DIR = Path(__file__).resolve().parents[4] / "docs"
_DEFAULT_DOCS_PAGES = (
    "user-guide/index.md,user-guide/concepts.md,user-guide/playbooks.md,user-guide/run.md"
)


def chat_enabled() -> bool:
    load_dotenv()
    return os.environ.get("CHAT_ENABLED", "false").lower() == "true"


def chat_base_url() -> str:
    """The base URL of an OpenAI-compatible API, e.g. http://localhost:11434/v1 for Ollama."""
    load_dotenv()
    return os.environ["CHAT_BASE_URL"]


def chat_model() -> str:
    load_dotenv()
    return os.environ["CHAT_MODEL"]


def chat_api_key() -> str | None:
    load_dotenv()
    return os.environ.get("CHAT_API_KEY") or None


def chat_max_output_tokens() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_OUTPUT_TOKENS", "400"))


def chat_max_messages() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_MESSAGES", "12"))


def chat_max_message_chars() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_MESSAGE_CHARS", "2000"))


def chat_max_history_chars() -> int:
    """The most characters one request's messages may hold in total."""
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_HISTORY_CHARS", "6000"))


def chat_sql_enabled() -> bool:
    """Whether the model is also told how to answer a question about the open project's
    data with a SQL query, which the browser runs."""
    load_dotenv()
    return os.environ.get("CHAT_SQL_ENABLED", "false").lower() == "true"


def chat_max_record_chars() -> int:
    """The most characters of a project's component types and attributes the model is
    given. What is beyond it is left out."""
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_RECORD_CHARS", "4000"))


def chat_max_concurrent() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_CONCURRENT", "2"))


def chat_timeout_seconds() -> float:
    """How long to wait for the model's next chunk, and for a whole reply."""
    load_dotenv()
    return float(os.environ.get("CHAT_TIMEOUT_SECONDS", "120"))


def chat_docs_dir() -> Path:
    load_dotenv()
    return Path(os.environ.get("CHAT_DOCS_DIR") or _REPO_DOCS_DIR)


def chat_docs_pages() -> list[str]:
    """The documentation pages the model answers from, relative to chat_docs_dir(), in
    the order they go into the prompt."""
    load_dotenv()
    pages = os.environ.get("CHAT_DOCS_PAGES") or _DEFAULT_DOCS_PAGES
    return [page.strip() for page in pages.split(",") if page.strip()]


def chat_docs_max_chars() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_DOCS_MAX_CHARS", "20000"))


@lru_cache
def get_chat_client() -> httpx2.Client:
    # The first chunk of a reply can take a while: a local model first has to load and
    # read the whole prompt. Connecting should not.
    return httpx2.Client(
        base_url=chat_base_url(), timeout=httpx2.Timeout(chat_timeout_seconds(), connect=5.0)
    )


@lru_cache
def get_chat_slots() -> threading.BoundedSemaphore:
    """One slot per reply being generated. Process-wide, which is server-wide while the
    app runs as a single process."""
    return threading.BoundedSemaphore(chat_max_concurrent())
