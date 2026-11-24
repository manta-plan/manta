from collections.abc import Iterator

from fastapi import APIRouter, Depends, Security
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.routes.v1.requests.chat_request import ChatRequest
from manta.services.auth_service import authenticated_user
from manta.services.chat_service import (
    ChatService,
    chat_slot,
    chat_status,
    check_message_limits,
    describe_record,
    require_chat_enabled,
)
from manta.services.results.chat_result import GetChatStatusResult

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Security(authenticated_user)])


def checked_request(request: ChatRequest) -> ChatRequest:
    check_message_limits([message.model_dump() for message in request.messages])
    return request


@router.get("/status", response_model=GetChatStatusResult)
def get_chat_status() -> GetChatStatusResult:
    return chat_status()


@router.post(
    "/messages",
    response_class=EventSourceResponse,
    dependencies=[Depends(require_chat_enabled)],
    responses={
        404: {"description": "Chat is not enabled in this deployment"},
        429: {"description": "Every reply slot is taken; see the Retry-After header"},
    },
)
def create_chat_message(
    request: ChatRequest = Depends(checked_request),
    _slot: None = Depends(chat_slot),
    service: ChatService = Depends(),
    db: Session = Depends(get_db_session),
) -> Iterator[ServerSentEvent]:
    """Streams the model's reply as server-sent events, each with a JSON payload:

    - `delta`, `{"text": ...}`: the next piece of the reply.
    - `done`, `{"finish_reason": "stop" | "length"}`: the reply is complete. `length`
      means it was cut off at the output limit. Always the last event.
    - `error`, `{"code": "model_unavailable" | "timeout", "message": ...}`: the model
      failed part-way. Always the last event.

    A stream that ends without `done` or `error` was interrupted. The backend keeps no
    conversation: send the earlier turns the model should remember with each question,
    within the limits GET /v1/chat/status reports.

    With `record`, and where the status reports `sql_enabled`, the model may answer a
    question about the project's data with one SQL query in a ```sql block. The backend
    never runs it: the client does, with the user's own access to the data.
    """
    # The session authenticated_user() used stays open until the response ends, which
    # here is as long as the model takes. Hand its connection back first.
    db.close()
    record = request.record and describe_record(**request.record.model_dump())
    messages = [message.model_dump() for message in request.messages]
    for event in service.stream_reply(messages, record):
        yield ServerSentEvent(event=event.event, data=event.data)
