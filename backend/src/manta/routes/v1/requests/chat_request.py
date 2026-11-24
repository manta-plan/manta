from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    """Who wrote the message: the person, or the model in an earlier reply. There is
    deliberately no `system` role: the backend alone writes the model's instructions."""

    content: str = Field(min_length=1)


# What a project's data may be called: short, and in the characters such names use.
# The backend puts these names into the model's instructions, so they are kept from
# holding more than a few words. Like a forged history, a forged name reaches no
# further than the sender's own reply.
_NAME = r"^[A-Za-z0-9_]{1,40}$"
_LABEL = r"^[A-Za-z0-9_.+/%\- ]{0,40}$"


class ChatRecordComponents(BaseModel):
    ctype: str = Field(pattern=_NAME)
    """A kind of component the project has, e.g. `Generator`."""

    carriers: list[Annotated[str, Field(pattern=_LABEL)]] = Field(max_length=60)


class ChatRecordAttribute(BaseModel):
    name: str = Field(pattern=_NAME)
    """An attribute the project has values for, read as the view `attributes.<name>`."""

    unit: str = Field(default="", pattern=_LABEL)
    subject: str = Field(pattern=_NAME)
    """The dimension a value belongs to, e.g. `entity` or `bus`."""

    series: bool = False
    """Whether the attribute has a value per snapshot."""


class ChatRecord(BaseModel):
    """What the open project's data contains, for a question the model answers with a
    SQL query: names only, never values."""

    components: list[ChatRecordComponents] = Field(max_length=40)
    attributes: list[ChatRecordAttribute] = Field(min_length=1, max_length=200)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    """The conversation so far, oldest first, ending with the question to answer. The
    backend keeps no conversation, so the client resends the turns it wants the model to
    remember, within the limits GET /v1/chat/status reports."""

    record: ChatRecord | None = None
    """Send it where GET /v1/chat/status reports `sql_enabled`, to let the model answer a
    question about the data with a SQL query. Ignored otherwise."""

    @model_validator(mode="after")
    def _ends_with_a_user_message(self) -> Self:
        if self.messages[-1].role != "user":
            raise ValueError("the last message must have the role 'user'")
        return self
