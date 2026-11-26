from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessageRequest(BaseModel):
    # Only what a person and the model said. The `system` message is the server's,
    # and tool calls and tool results never leave it, so none of them can be sent:
    # the roles are a closed list and unknown fields (`tool_calls`, `name`, ...)
    # are refused instead of being quietly dropped.
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str


class SendChatMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessageRequest] = Field(min_length=1)
    """The conversation so far, oldest first, ending with the user's new message.
    Nothing of it is stored, so the client sends the earlier turns along each time
    and leaves out the oldest to stay within `max_messages`, `max_message_chars`
    and `max_history_chars` of GET /v1/chat/status. Past those the request is
    refused, not cut."""

    run_uuid: UUID | None = None
    """The run the user is looking at, if any. A run that is not theirs is ignored."""

    @model_validator(mode="after")
    def _ends_with_a_message_of_the_user(self) -> Self:
        last = self.messages[-1]
        if last.role != "user" or not last.content.strip():
            raise ValueError("The last message must be a message from the user with text in it.")
        return self
