import { ApiError } from "../../api/manta";
import { streamChatReply } from "./api";
import { interruptedNote } from "./storage";
import type { ChatCitation, ChatHistoryMessage, ChatStatus, ChatStreamEvent } from "./types";

/** `streaming` while the reply is written; `stopped` by the user; `interrupted` by the connection. */
export type ChatMessageStatus = "streaming" | "complete" | "stopped" | "interrupted" | "error";

/** One thing the assistant looked up, in the server's plain words. */
export type ChatToolStep = {
  /** The tool, to match its result to its call; empty on a conversation read back from storage. */
  name: string;
  label: string;
  state: "running" | "done" | "failed";
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status: ChatMessageStatus;
  tools: ChatToolStep[];
  citations: ChatCitation[];
  /** Why the reply stopped, failed or was cut short, in plain words; null when it just ended. */
  note: string | null;
};

export type ChatState = {
  messages: ChatMessage[];
  /** A reply is being fetched or written: the last message is the assistant's, still open. */
  isStreaming: boolean;
};

export type ChatAction =
  | { type: "send"; userId: string; assistantId: string; text: string }
  /** Asks the last question again, in place of the reply that failed. */
  | { type: "retry"; assistantId: string }
  | { type: "event"; event: ChatStreamEvent }
  | { type: "stopped" }
  | { type: "failed"; note: string }
  /** Empties the conversation. */
  | { type: "clear" };

export const initialChatState: ChatState = { messages: [], isStreaming: false };

const errorNotes = {
  model_unavailable: "The assistant's model is not available right now. Try again in a moment.",
  timeout: "The answer took too long and was stopped. Try again, or ask a shorter question.",
  internal: "Something went wrong while answering. Try again.",
};

function openReply(id: string): ChatMessage {
  return {
    id,
    role: "assistant",
    text: "",
    status: "streaming",
    tools: [],
    citations: [],
    note: null,
  };
}

/** Whether a reply ended in a way that asking again can fix. */
export function canRetry(message: ChatMessage) {
  return (
    message.role === "assistant" && (message.status === "error" || message.status === "interrupted")
  );
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  if (action.type === "clear") {
    return initialChatState;
  }

  if (action.type === "send") {
    if (state.isStreaming) {
      return state;
    }

    return {
      isStreaming: true,
      messages: [
        ...state.messages,
        {
          id: action.userId,
          role: "user",
          text: action.text,
          status: "complete",
          tools: [],
          citations: [],
          note: null,
        },
        openReply(action.assistantId),
      ],
    };
  }

  const last = state.messages.at(-1);

  if (action.type === "retry") {
    if (state.isStreaming || last === undefined || !canRetry(last)) {
      return state;
    }

    return {
      isStreaming: true,
      messages: [...state.messages.slice(0, -1), openReply(action.assistantId)],
    };
  }

  // Everything else changes the open reply; with none open there is nothing to change.
  if (!state.isStreaming || last === undefined) {
    return state;
  }

  const reply = applyToReply(last, action);

  return {
    isStreaming: reply.status === "streaming",
    messages: [...state.messages.slice(0, -1), reply],
  };
}

function applyToReply(
  reply: ChatMessage,
  action: Exclude<ChatAction, { type: "send" } | { type: "retry" } | { type: "clear" }>,
): ChatMessage {
  if (action.type === "stopped") {
    return { ...reply, status: "stopped", note: "Stopped." };
  }

  if (action.type === "failed") {
    return { ...reply, status: "error", note: action.note };
  }

  const { event } = action;

  switch (event.type) {
    case "text_delta":
      return { ...reply, text: reply.text + event.text };
    case "tool_call":
      return {
        ...reply,
        tools: [...reply.tools, { name: event.name, label: event.label, state: "running" }],
      };
    case "tool_result_summary": {
      // The result belongs to the earliest call of that tool still running.
      const index = reply.tools.findIndex(
        (tool) => tool.name === event.name && tool.state === "running",
      );

      if (index === -1) {
        return reply;
      }

      return {
        ...reply,
        tools: reply.tools.map((tool, toolIndex) =>
          toolIndex === index ? { ...tool, state: event.ok ? "done" : "failed" } : tool,
        ),
      };
    }
    case "citation": {
      if (reply.citations.some((citation) => citation.index === event.index)) {
        return reply;
      }

      const { type: _type, ...citation } = event;

      return {
        ...reply,
        citations: [...reply.citations, citation].sort((a, b) => a.index - b.index),
      };
    }
    case "usage":
      return reply;
    case "error":
      return { ...reply, status: "error", note: errorNotes[event.code] };
    case "interrupted":
      return { ...reply, status: "interrupted", note: interruptedNote };
    case "done":
      switch (event.finish_reason) {
        case "length":
          return {
            ...reply,
            status: "complete",
            note: "The answer reached the length limit and was cut short.",
          };
        case "tool_limit":
          return {
            ...reply,
            status: "complete",
            note: "Rai reached the limit of lookups for one answer, so this may be incomplete.",
          };
        default:
          return { ...reply, status: "complete" };
      }
  }
}

/** How many questions the user has left today; null when the deployment sets no daily limit. */
export function questionsLeft(status: ChatStatus) {
  return status.daily_message_limit > 0
    ? Math.max(0, status.daily_message_limit - status.messages_used_today)
    : null;
}

type HistoryLimits = Pick<ChatStatus, "max_messages" | "max_message_chars" | "max_history_chars">;

/**
 * What to send for `question`: the exchanges before it that the server can use, then the question.
 * An exchange is a question with the answer it got. One whose reply failed, was interrupted or
 * has no text is left out, question included, so that the roles alternate; a stopped reply that
 * has text counts as an answer. Tool activity, sources and notes never go out. To fit the limits,
 * whole exchanges are dropped from the oldest on, and text is never cut: the history ends at the
 * first exchange, counted back from the newest, that does not fit. The question always goes out.
 */
export function buildHistory(
  previous: ChatMessage[],
  question: string,
  limits: HistoryLimits,
): ChatHistoryMessage[] {
  const history: ChatHistoryMessage[] = [{ role: "user", content: question }];
  let chars = question.length;

  for (let index = previous.length - 1; index >= 1; index--) {
    const answer = previous[index];
    const asked = previous[index - 1];

    if (answer.role !== "assistant" || asked.role !== "user") {
      continue;
    }

    // The pair is taken as a whole from here on.
    index--;

    const content = answer.text.trim();

    if (content === "" || (answer.status !== "complete" && answer.status !== "stopped")) {
      continue;
    }

    chars += asked.text.length + content.length;

    if (
      history.length + 2 > limits.max_messages ||
      chars > limits.max_history_chars ||
      asked.text.length > limits.max_message_chars ||
      content.length > limits.max_message_chars
    ) {
      break;
    }

    history.unshift({ role: "user", content: asked.text }, { role: "assistant", content });
  }

  return history;
}

export type ChatTurn = {
  /** The conversation to send, ending in the question: see `buildHistory`. */
  messages: ChatHistoryMessage[];
  runUuid: string | null;
  signal: AbortSignal;
};

/**
 * Asks one question and feeds the reply to `dispatch` until it ends, is stopped or fails. The
 * server does not report a stop, so an aborted `signal` is what marks the reply as stopped.
 * `refreshStatus` reads the chat status again afterwards: each question counts against the daily
 * limit, and chat may have been turned off.
 */
export async function runChatTurn(
  turn: ChatTurn,
  dispatch: (action: ChatAction) => void,
  refreshStatus: () => Promise<unknown>,
): Promise<void> {
  try {
    for await (const event of streamChatReply(turn.messages, turn.runUuid, turn.signal)) {
      dispatch({ type: "event", event });
    }
  } catch (error) {
    dispatch(
      turn.signal.aborted ? { type: "stopped" } : { type: "failed", note: describeFailure(error) },
    );
  }

  void refreshStatus().catch(() => {});
}

function describeFailure(error: unknown) {
  if (!(error instanceof ApiError)) {
    return "Rai could not be reached. Check your connection and try again.";
  }

  switch (error.status) {
    case 401:
      return "Your session has ended. Sign in again to keep chatting.";
    case 404:
      return "Chat is not available right now.";
    case 422:
      return "Rai could not accept that message. Shorten it, or clear the chat and ask again.";
    case 429: {
      if (error.code === "daily_limit") {
        return "You have used all of today's questions. Try again tomorrow.";
      }

      const wait =
        error.retryAfterSeconds === null
          ? "in a moment"
          : `in ${error.retryAfterSeconds} ${error.retryAfterSeconds === 1 ? "second" : "seconds"}`;

      return `Rai is busy answering other questions. Try again ${wait}.`;
    }
    default:
      return "Rai could not answer. Try again.";
  }
}
