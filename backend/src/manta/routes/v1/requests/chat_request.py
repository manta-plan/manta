from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    """Who wrote the message: the person, or the model in an earlier reply. There is
    deliberately no `system` role: the backend alone writes the model's instructions."""

    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    """The conversation so far, oldest first, ending with the question to answer. The
    backend keeps no conversation, so the client resends the turns it wants the model to
    remember, within the limits GET /v1/chat/status reports."""

    @model_validator(mode="after")
    def _ends_with_a_user_message(self) -> Self:
        if self.messages[-1].role != "user":
            raise ValueError("the last message must have the role 'user'")
        return self
