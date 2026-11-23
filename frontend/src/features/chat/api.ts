import { useEffect, useState } from "react";
import { getJson, postStream } from "../../api/manta";
import { readSseEvents } from "./sse";

/** GET /v1/chat/status: whether this deployment has a model, and its limits. */
export interface ChatStatus {
  enabled: boolean;
  max_messages: number;
  max_message_chars: number;
  max_history_chars: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export type ChatReplyEvent =
  | { type: "delta"; text: string }
  /** `length`: the reply was cut off at the server's output limit. */
  | { type: "done"; finishReason: "stop" | "length" }
  | { type: "error"; message: string };

/**
 * The chat's status, `undefined` while it loads. A failed request reads as
 * `null`: the chat is then shown as not available, like a disabled one.
 */
export function useChatStatus(): ChatStatus | null | undefined {
  const [status, setStatus] = useState<ChatStatus | null>();

  useEffect(() => {
    let current = true;
    getJson<ChatStatus>("/v1/chat/status")
      .then((result) => current && setStatus(result))
      .catch(() => current && setStatus(null));
    return () => {
      current = false;
    };
  }, []);

  return status;
}

/**
 * The turns to send with a question, within the server's limits. The server
 * keeps no conversation, so what is sent is all the model remembers: the
 * oldest turns are left out first, and what remains starts with a question.
 */
export function fitHistory(turns: ChatTurn[], limits: ChatStatus): ChatTurn[] {
  let kept = turns.map((turn) => ({
    ...turn,
    content: turn.content.slice(0, limits.max_message_chars),
  }));
  const size = () => kept.reduce((total, turn) => total + turn.content.length, 0);

  while (
    kept.length > 1 &&
    (kept.length > limits.max_messages ||
      size() > limits.max_history_chars ||
      kept[0].role === "assistant")
  ) {
    kept = kept.slice(1);
  }
  return kept;
}

/**
 * Asks the model and yields its reply as it is written: `delta` events, then
 * one `done` or `error`. Throws an `ApiError` when the request is refused
 * before the reply starts (e.g. 429 while the model is busy), and whatever
 * `fetch` throws when it is aborted through `signal`.
 */
export async function* streamChatReply(
  turns: ChatTurn[],
  signal: AbortSignal,
): AsyncGenerator<ChatReplyEvent> {
  const response = await postStream("/v1/chat/messages", { messages: turns }, signal);

  if (response.body !== null) {
    for await (const { event, data } of readSseEvents(response.body)) {
      const payload = JSON.parse(data) as Record<string, string>;

      if (event === "delta") {
        yield { type: "delta", text: payload.text };
      } else if (event === "done") {
        yield {
          type: "done",
          finishReason: payload.finish_reason === "length" ? "length" : "stop",
        };
        return;
      } else if (event === "error") {
        yield { type: "error", message: payload.message };
        return;
      }
    }
  }

  // The stream ended without saying why, e.g. the connection dropped.
  yield { type: "error", message: "The reply was interrupted. Try again." };
}
