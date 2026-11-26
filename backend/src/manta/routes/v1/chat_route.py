from collections.abc import Iterator

from fastapi import APIRouter, Depends, Security
from fastapi.sse import EventSourceResponse, ServerSentEvent

from manta.entities import User
from manta.routes.v1.requests.chat_request import SendChatMessagesRequest
from manta.services.auth_service import authenticated_user
from manta.services.chat_service import ChatService, ChatTurn
from manta.services.results.chat_result import GetChatStatusResult

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/status", response_model=GetChatStatusResult)
def get_chat_status(
    user: User = Security(authenticated_user),
    service: ChatService = Depends(),
) -> GetChatStatusResult:
    return service.get_status(user=user)


def chat_turn(
    request: SendChatMessagesRequest,
    user: User = Security(authenticated_user),
    service: ChatService = Depends(),
) -> Iterator[ChatTurn]:
    # A dependency, not part of the route below, for two reasons. The route is a
    # generator, which only starts running once the 200 is on its way, so a
    # message has to be refused here to be refused with a 404, 422 or 429. And a
    # client that goes away leaves that generator hanging without closing it,
    # while a dependency is always exited, so that is where the answer is stopped.
    turn = service.start_turn(
        messages=[(message.role, message.content) for message in request.messages],
        run_uuid=request.run_uuid,
        user=user,
    )
    try:
        yield turn
    finally:
        service.end_turn(turn)


@router.post(
    "/messages",
    response_class=EventSourceResponse,
    responses={
        404: {"description": "Chat is disabled."},
        429: {
            "description": (
                "The user's daily message limit is reached (`detail.code` is "
                "`daily_limit`), or too many answers are being generated "
                "(`concurrency_limit`). `Retry-After` says when to try again."
            )
        },
    },
)
def send_chat_messages(
    turn: ChatTurn = Depends(chat_turn),
    service: ChatService = Depends(),
) -> Iterator[ServerSentEvent]:
    """Sends the conversation so far, ending with the user's new message, and streams
    the answer as server-sent events, each with JSON data:

    - `text_delta`: `{"text"}`, the next piece of the answer.
    - `tool_call`: `{"name", "label"}`, a lookup that has started.
    - `tool_result_summary`: `{"name", "ok"}`, that lookup has ended.
    - `citation`: `{"index", "title", "heading_path", "url"}`, a documentation section
      the answer can refer to as `[index]`. `url` is relative to the docs root.
    - `usage`: `{"input_tokens", "output_tokens"}`, when the model reports them.
    - `error`: `{"code", "message"}`, with code `model_unavailable`, `timeout` or
      `internal`. Ends the stream.
    - `done`: `{"finish_reason"}`, with `stop`, `length` or `tool_limit`. Ends the stream.

    A stream that ends without `done` or `error` was interrupted.

    Nothing is stored: the client keeps the conversation and sends it along each time.
    """
    for event in service.stream_reply(turn):
        yield ServerSentEvent(event=event.event, data=event)
