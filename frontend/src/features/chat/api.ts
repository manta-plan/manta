import useSWR from "swr";
import { getJson, postStream } from "../../api/manta";
import { isObject } from "../../utils/jsonObject";
import { readSseEvents, type SseEvent } from "./sse";
import type {
  ChatErrorCode,
  ChatFinishReason,
  ChatHistoryMessage,
  ChatStatus,
  ChatStreamEvent,
} from "./types";

const chatStatusUrl = "/v1/chat/status";

const errorCodes: readonly string[] = ["model_unavailable", "timeout", "internal"];
const finishReasons: readonly string[] = ["stop", "length", "tool_limit"];

/** Reads the chat status, refusing a body that is not one. */
export async function getChatStatus(): Promise<ChatStatus> {
  const body = await getJson<unknown>(chatStatusUrl);

  if (
    !isObject(body) ||
    typeof body.enabled !== "boolean" ||
    typeof body.max_messages !== "number" ||
    typeof body.max_message_chars !== "number" ||
    typeof body.max_history_chars !== "number" ||
    typeof body.daily_message_limit !== "number" ||
    typeof body.messages_used_today !== "number"
  ) {
    throw new Error("The chat status is not in the expected form.");
  }

  return {
    enabled: body.enabled,
    max_messages: body.max_messages,
    max_message_chars: body.max_message_chars,
    max_history_chars: body.max_history_chars,
    daily_message_limit: body.daily_message_limit,
    messages_used_today: body.messages_used_today,
  };
}

/**
 * Whether chat is on, and the signed-in user's limits. `status` stays undefined while it loads
 * and when the request fails; `refresh` reads it again and resolves to the new status.
 */
export function useChatStatus() {
  const { data, error, isLoading, mutate } = useSWR(chatStatusUrl, getChatStatus, {
    revalidateOnFocus: false,
    errorRetryCount: 3,
  });

  return {
    status: data,
    hasFailed: data === undefined && error !== undefined,
    isLoading,
    refresh: () => mutate(),
  };
}

/**
 * Sends the conversation, ending in the new question, and yields the reply as it is written. The
 * server keeps nothing between requests, so `messages` is all it knows: see `buildHistory`. The
 * stream always ends with `done`, `error` or `interrupted`. A failure before the stream starts
 * throws an `ApiError`; aborting `signal` throws the abort.
 */
export async function* streamChatReply(
  messages: ChatHistoryMessage[],
  runUuid: string | null,
  signal: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const response = await postStream("/v1/chat/messages", { messages, run_uuid: runUuid }, signal);

  if (response.body !== null) {
    try {
      for await (const sseEvent of readSseEvents(response.body)) {
        const event = toChatStreamEvent(sseEvent);

        if (event === null) {
          continue;
        }

        yield event;

        if (event.type === "done" || event.type === "error") {
          return;
        }
      }
    } catch (error) {
      if (signal.aborted) {
        throw error;
      }
      // The connection dropped in the middle of the reply.
    }
  }

  yield { type: "interrupted" };
}

/**
 * The typed event of a server-sent one. Null for an event this client does not know, and for one
 * whose data is not what its name promises: both are skipped rather than shown.
 */
export function toChatStreamEvent({ event, data }: SseEvent): ChatStreamEvent | null {
  let body: unknown;

  try {
    body = JSON.parse(data);
  } catch {
    return null;
  }

  if (!isObject(body)) {
    return null;
  }

  switch (event) {
    case "text_delta":
      return typeof body.text === "string" ? { type: "text_delta", text: body.text } : null;
    case "tool_call":
      return typeof body.name === "string" && typeof body.label === "string"
        ? { type: "tool_call", name: body.name, label: body.label }
        : null;
    case "tool_result_summary":
      return typeof body.name === "string" && typeof body.ok === "boolean"
        ? { type: "tool_result_summary", name: body.name, ok: body.ok }
        : null;
    case "citation": {
      const headingPath = toHeadingPath(body.heading_path);

      return typeof body.index === "number" &&
        typeof body.title === "string" &&
        headingPath !== null &&
        typeof body.url === "string"
        ? {
            type: "citation",
            index: body.index,
            title: body.title,
            heading_path: headingPath,
            url: body.url,
          }
        : null;
    }
    case "usage":
      return typeof body.input_tokens === "number" && typeof body.output_tokens === "number"
        ? { type: "usage", input_tokens: body.input_tokens, output_tokens: body.output_tokens }
        : null;
    case "error":
      // An error with an unknown code still ends the reply.
      return {
        type: "error",
        code:
          typeof body.code === "string" && errorCodes.includes(body.code)
            ? (body.code as ChatErrorCode)
            : "internal",
        message: typeof body.message === "string" ? body.message : "",
      };
    case "done":
      return {
        type: "done",
        finish_reason:
          typeof body.finish_reason === "string" && finishReasons.includes(body.finish_reason)
            ? (body.finish_reason as ChatFinishReason)
            : "stop",
      };
    default:
      return null;
  }
}

// The headings leading to a cited section, as one line. The contract does not say whether the
// server sends them joined or as a list, so both are read.
function toHeadingPath(value: unknown) {
  if (typeof value === "string") {
    return value;
  }

  if (Array.isArray(value) && value.every((part) => typeof part === "string")) {
    return value.join(" › ");
  }

  return null;
}
