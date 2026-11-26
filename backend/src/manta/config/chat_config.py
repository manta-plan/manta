import os
import threading
from functools import lru_cache
from pathlib import Path

import httpx2
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[4]


def chat_embed_base_url() -> str:
    """An OpenAI-compatible API base, by default the local Ollama of
    docker/compose-dev-chat.yaml."""
    load_dotenv()
    return os.environ.get("CHAT_EMBED_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def chat_embed_model() -> str:
    load_dotenv()
    return os.environ.get("CHAT_EMBED_MODEL", "bge-m3")


def chat_embed_api_key() -> str | None:
    """Unset for Ollama, which takes no key."""
    load_dotenv()
    return os.environ.get("CHAT_EMBED_API_KEY") or None


def chat_docs_dir() -> Path:
    load_dotenv()
    return Path(os.environ.get("CHAT_DOCS_DIR", _REPO_ROOT / "docs"))


def chat_docs_sections() -> list[str]:
    """The folders below the docs folder that are indexed. `contributing` and
    `reference` are left out by default: end users rarely ask about them."""
    load_dotenv()
    sections = os.environ.get("CHAT_DOCS_SECTIONS", "user-guide,installation,explanation")
    return [s.strip() for s in sections.split(",") if s.strip()]


def chat_rag_top_k() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_RAG_TOP_K", "5"))


def chat_rag_min_score() -> float:
    """The lowest fused score a docs hit needs to reach the model. A chunk that only
    one of the two rankings found scores at most 1/61 (about 0.016), which is what an
    off-topic question gets, so the default keeps chunks both rankings found."""
    load_dotenv()
    return float(os.environ.get("CHAT_RAG_MIN_SCORE", "0.02"))


def chat_enabled() -> bool:
    """Off unless set. Also the kill switch: turning it off makes every chat route
    except the status answer 404."""
    load_dotenv()
    return os.environ.get("CHAT_ENABLED", "false").lower() == "true"


def chat_base_url() -> str:
    """An OpenAI-compatible API base, by default the local Ollama of
    docker/compose-dev-chat.yaml. A hosted provider is a change of this value."""
    load_dotenv()
    return os.environ.get("CHAT_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def chat_model() -> str:
    load_dotenv()
    return os.environ.get("CHAT_MODEL", "manta-chat")


def chat_api_key() -> str | None:
    """Unset for Ollama, which takes no key."""
    load_dotenv()
    return os.environ.get("CHAT_API_KEY") or None


def chat_max_output_tokens() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_OUTPUT_TOKENS", "400"))


def chat_max_messages() -> int:
    """The most messages one request may carry: the new one and the earlier turns
    the client sends along."""
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_MESSAGES", "12"))


def chat_max_message_chars() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_MESSAGE_CHARS", "2000"))


def chat_max_history_chars() -> int:
    """The most characters all messages of one request may have together. The client
    leaves out its oldest turns to fit; a request over the limit is refused. Sized
    for the 8192-token context of the local model."""
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_HISTORY_CHARS", "6000"))


def chat_max_tool_calls() -> int:
    """Tool calls per answer. After that the model must answer without tools."""
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_TOOL_CALLS", "6"))


def chat_max_tool_chars() -> int:
    """How much tool output one answer may put in the prompt, over all its tool
    calls. Each tool also has its own cap. Without this, two large results overflow
    the model's context, and the model server then silently drops the start of the
    prompt, which is where the rules are."""
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_TOOL_CHARS", "12000"))


def chat_max_concurrent() -> int:
    load_dotenv()
    return int(os.environ.get("CHAT_MAX_CONCURRENT", "2"))


def chat_timeout_seconds() -> float:
    """The longest one answer may take, including its tool calls."""
    load_dotenv()
    return float(os.environ.get("CHAT_TIMEOUT_SECONDS", "120"))


def chat_daily_message_limit() -> int:
    """Messages one user may send in any 24 hours. Counted in memory, per process
    (see ChatUsageWindow)."""
    load_dotenv()
    return int(os.environ.get("CHAT_DAILY_MESSAGE_LIMIT", "50"))


@lru_cache
def get_chat_http_client() -> httpx2.Client:
    """One client for the chat model and the embeddings API. Each request sets its
    own read timeout, so this one only bounds connecting."""
    return httpx2.Client(timeout=httpx2.Timeout(chat_timeout_seconds(), connect=10))


@lru_cache
def get_chat_slots() -> threading.BoundedSemaphore:
    """Bounds the answers generated at once in this process. Each one holds a worker
    thread, and a local model serves them one after the other anyway."""
    return threading.BoundedSemaphore(chat_max_concurrent())
