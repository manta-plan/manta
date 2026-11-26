from typing import ClassVar, Literal

from pydantic import BaseModel


class GetChatStatusResult(BaseModel):
    enabled: bool
    max_messages: int
    """The most messages one request may carry, the new one included."""

    max_message_chars: int
    max_history_chars: int
    """The most characters all messages of one request may have together."""

    daily_message_limit: int
    """Messages the user may send in any 24 hours."""

    messages_used_today: int
    """Messages the user sent in the last 24 hours, as far as this server process
    has seen: the count is kept in memory."""


class ChatCitationResult(BaseModel):
    """A documentation section the model was given for this answer."""

    event: ClassVar[str] = "citation"

    index: int
    """The number the model refers to the section by, from 1, within one answer."""

    title: str
    heading_path: str
    url: str
    """Relative to the docs root, e.g. `user-guide/run.md#start-a-run`."""


class ChatToolResult(BaseModel):
    """What one tool call gave back, for ChatService only: `content` goes to the
    model, never to the client."""

    name: str
    ok: bool
    content: str
    citations: list[ChatCitationResult] = []


class ChatTextDeltaResult(BaseModel):
    event: ClassVar[str] = "text_delta"

    text: str


class ChatToolCallResult(BaseModel):
    event: ClassVar[str] = "tool_call"

    name: str
    label: str
    """What the tool is doing in plain words, e.g. "Checking run logs". Never its
    arguments."""


class ChatToolResultSummaryResult(BaseModel):
    event: ClassVar[str] = "tool_result_summary"

    name: str
    ok: bool


class ChatUsageResult(BaseModel):
    event: ClassVar[str] = "usage"

    input_tokens: int
    output_tokens: int


class ChatErrorResult(BaseModel):
    event: ClassVar[str] = "error"

    code: Literal["model_unavailable", "timeout", "internal"]
    message: str


class ChatDoneResult(BaseModel):
    event: ClassVar[str] = "done"

    finish_reason: Literal["stop", "length", "tool_limit"]


ChatEventResult = (
    ChatTextDeltaResult
    | ChatToolCallResult
    | ChatToolResultSummaryResult
    | ChatCitationResult
    | ChatUsageResult
    | ChatErrorResult
    | ChatDoneResult
)
"""One server-sent event of an answer: `event` is its name, the fields its data."""
