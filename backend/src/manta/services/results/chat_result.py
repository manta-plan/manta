from typing import Literal

from pydantic import BaseModel


class GetChatStatusResult(BaseModel):
    enabled: bool
    """Whether this deployment has a model configured. When false, POST
    /v1/chat/messages answers 404."""

    sql_enabled: bool
    """Whether the model answers a question about the open project's data with a SQL
    query, when the request describes that data in `record`."""

    max_messages: int
    max_message_chars: int
    max_history_chars: int
    """The most characters all messages of one request may hold in total."""


class ChatEventResult(BaseModel):
    """One server-sent event of a reply: its event name and its JSON payload. POST
    /v1/chat/messages documents the three events."""

    event: Literal["delta", "done", "error"]
    data: dict[str, str]
