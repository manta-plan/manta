from typing import Literal

from pydantic import BaseModel


class GetChatStatusResult(BaseModel):
    enabled: bool
    """Whether this deployment has a model configured. When false, POST
    /v1/chat/messages answers 404."""

    max_messages: int
    max_message_chars: int
    max_history_chars: int
    """The most characters all messages of one request may hold in total."""


class ChatEventResult(BaseModel):
    """One server-sent event of a reply: its event name and its JSON payload. POST
    /v1/chat/messages documents the three events."""

    event: Literal["delta", "done", "error"]
    data: dict[str, str]
