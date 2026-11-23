import json
import threading
from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest
from fastapi import HTTPException

from manta.services.chat_service import (
    ChatService,
    chat_slot,
    chat_status,
    check_message_limits,
    require_chat_enabled,
    system_prompt,
)

QUESTION = [{"role": "user", "content": "How do I start a run?"}]


@pytest.fixture(autouse=True)
def chat_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A chat configured with one small documentation page. Returns the docs directory."""
    (tmp_path / "guide.md").write_text("# Guide\n\nClick Run to start a run.\n")
    monkeypatch.setenv("CHAT_MODEL", "test-model")
    monkeypatch.setenv("CHAT_DOCS_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DOCS_PAGES", "guide.md")
    for name in (
        "CHAT_API_KEY",
        "CHAT_MAX_MESSAGES",
        "CHAT_MAX_MESSAGE_CHARS",
        "CHAT_MAX_HISTORY_CHARS",
        "CHAT_DOCS_MAX_CHARS",
    ):
        monkeypatch.delenv(name, raising=False)
    system_prompt.cache_clear()
    yield tmp_path
    system_prompt.cache_clear()


def _chunk(text: str | None = None, finish_reason: str | None = None) -> str:
    delta = {} if text is None else {"content": text}
    return (
        f"data: {json.dumps({'choices': [{'delta': delta, 'finish_reason': finish_reason}]})}\n\n"
    )


def _model(*chunks: str, requests: list[httpx2.Request] | None = None) -> ChatService:
    """A service whose model answers every request with the given stream."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        return httpx2.Response(200, content="".join(chunks).encode())

    return _service(handler)


def _service(handler: Callable[[httpx2.Request], httpx2.Response]) -> ChatService:
    return ChatService(
        httpx2.Client(base_url="http://model.test/v1", transport=httpx2.MockTransport(handler))
    )


def _events(service: ChatService) -> list[tuple[str, dict[str, str]]]:
    return [(event.event, event.data) for event in service.stream_reply(QUESTION)]


def test_stream_reply_yields_the_models_text_then_done() -> None:
    # Given
    service = _model(
        _chunk("Click "), _chunk("Run."), _chunk(finish_reason="stop"), "data: [DONE]\n\n"
    )

    # When
    events = _events(service)

    # Then
    assert events == [
        ("delta", {"text": "Click "}),
        ("delta", {"text": "Run."}),
        ("done", {"finish_reason": "stop"}),
    ]


def test_stream_reply_reports_a_reply_cut_off_at_the_output_limit() -> None:
    # Given
    service = _model(_chunk("Click"), _chunk(finish_reason="length"))

    # When
    events = _events(service)

    # Then
    assert events[-1] == ("done", {"finish_reason": "length"})


def test_stream_reply_asks_the_configured_model_with_its_own_instructions_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("CHAT_MAX_OUTPUT_TOKENS", "123")
    requests: list[httpx2.Request] = []
    service = _model(_chunk(finish_reason="stop"), requests=requests)

    # When the same question is asked twice
    _events(service)
    _events(service)

    # Then
    first, second = (json.loads(request.content) for request in requests)
    assert str(requests[0].url) == "http://model.test/v1/chat/completions"
    assert first["model"] == "test-model"
    assert first["stream"] is True
    assert first["max_tokens"] == 123
    assert [message["role"] for message in first["messages"]] == ["system", "user"]
    assert first["messages"][1]["content"] == "How do I start a run?"
    # Byte-identical instructions let a model server reuse its work on them.
    assert first["messages"][0] == second["messages"][0]


@pytest.mark.parametrize(
    ("api_key", "expected"),
    [(None, None), ("secret", "Bearer secret")],
    ids=["no_key", "key"],
)
def test_stream_reply_sends_the_api_key_only_when_one_is_configured(
    monkeypatch: pytest.MonkeyPatch, api_key: str | None, expected: str | None
) -> None:
    # Given
    if api_key:
        monkeypatch.setenv("CHAT_API_KEY", api_key)
    requests: list[httpx2.Request] = []
    service = _model(_chunk(finish_reason="stop"), requests=requests)

    # When
    _events(service)

    # Then
    assert requests[0].headers.get("Authorization") == expected


def _server_error(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(500, json={"error": "internal details"})


def _unreachable(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("offline", request=request)


def _too_slow(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("too slow", request=request)


def _not_json(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, content=b"data: <html>\n\n")


def _cut_short(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, content=_chunk("Click").encode())


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (_server_error, "model_unavailable"),
        (_unreachable, "model_unavailable"),
        (_not_json, "model_unavailable"),
        (_cut_short, "model_unavailable"),
        (_too_slow, "timeout"),
    ],
)
def test_stream_reply_ends_with_an_error_event_when_the_model_fails(
    handler: Callable[[httpx2.Request], httpx2.Response], code: str
) -> None:
    # When
    events = _events(_service(handler))

    # Then it does not raise, and tells the client no more than which kind of failure
    name, data = events[-1]
    assert name == "error"
    assert data["code"] == code
    assert "internal details" not in data["message"]


def test_stream_reply_gives_up_once_the_whole_reply_takes_too_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a model that keeps writing, and no time left
    monkeypatch.setenv("CHAT_TIMEOUT_SECONDS", "-1")
    service = _model(_chunk("Click "), _chunk("Run."), _chunk(finish_reason="stop"))

    # When
    events = _events(service)

    # Then
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["code"] == "timeout"


def test_system_prompt_holds_the_pages_in_order_without_snippet_includes_or_bold(
    monkeypatch: pytest.MonkeyPatch, chat_config: Path
) -> None:
    # Given
    (chat_config / "more.md").write_text(
        '# More\n\n--8<-- "docs/figure.svg"\n\nSelect **New run**.\n'
    )
    monkeypatch.setenv("CHAT_DOCS_PAGES", "guide.md, more.md")

    # When
    prompt = system_prompt()

    # Then
    assert prompt.index("Click Run to start a run.") < prompt.index("# More")
    assert "Select New run." in prompt
    assert "--8<--" not in prompt


def test_system_prompt_refuses_a_missing_page(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setenv("CHAT_DOCS_PAGES", "missing.md")

    # When/Then
    with pytest.raises(RuntimeError, match=r"missing\.md"):
        system_prompt()


def test_system_prompt_refuses_pages_larger_than_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("CHAT_DOCS_MAX_CHARS", "10")

    # When/Then
    with pytest.raises(RuntimeError, match="CHAT_DOCS_MAX_CHARS"):
        system_prompt()


def test_system_prompt_fits_the_default_pages_into_the_default_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given the repository's own documentation. Fails when a default page is renamed, or
    # the pages outgrow the limit the default model's context was budgeted for.
    monkeypatch.delenv("CHAT_DOCS_DIR")
    monkeypatch.delenv("CHAT_DOCS_PAGES")

    # When
    prompt = system_prompt()

    # Then
    assert "user-guide/run.md" in prompt


def test_check_message_limits_accepts_messages_within_the_limits() -> None:
    # When/Then it does not raise
    check_message_limits(QUESTION)


@pytest.mark.parametrize(
    ("limit", "contents"),
    [
        ("CHAT_MAX_MESSAGES", ["a", "b", "c"]),
        ("CHAT_MAX_MESSAGE_CHARS", ["abc"]),
        ("CHAT_MAX_HISTORY_CHARS", ["ab", "ab"]),
    ],
)
def test_check_message_limits_refuses_messages_over_a_limit(
    monkeypatch: pytest.MonkeyPatch, limit: str, contents: list[str]
) -> None:
    # Given
    monkeypatch.setenv(limit, "2")
    messages = [{"role": "user", "content": content} for content in contents]

    # When/Then
    with pytest.raises(HTTPException) as error:
        check_message_limits(messages)
    assert error.value.status_code == 422


def test_chat_slot_refuses_a_reply_while_every_slot_is_taken() -> None:
    # Given one slot, held by a reply in progress
    slots = threading.BoundedSemaphore(1)
    in_progress = chat_slot(slots)
    next(in_progress)

    # When/Then
    with pytest.raises(HTTPException) as error:
        next(chat_slot(slots))
    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "10"}

    # And once that reply has ended, the slot is free again
    in_progress.close()
    next(chat_slot(slots))


def test_require_chat_enabled_answers_404_unless_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("CHAT_ENABLED", "false")

    # When/Then
    with pytest.raises(HTTPException) as error:
        require_chat_enabled()
    assert error.value.status_code == 404

    # And
    monkeypatch.setenv("CHAT_ENABLED", "true")
    require_chat_enabled()


def test_chat_status_reports_the_limits_even_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given no model configured at all
    monkeypatch.setenv("CHAT_ENABLED", "false")
    monkeypatch.delenv("CHAT_MODEL")
    monkeypatch.setenv("CHAT_MAX_MESSAGES", "4")

    # When
    result = chat_status()

    # Then
    assert result.enabled is False
    assert result.max_messages == 4
