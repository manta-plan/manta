/** `GET /v1/chat/status`. It answers when chat is disabled too. */
export type ChatStatus = {
  enabled: boolean;
  /** The most messages one request may carry, the new one included. */
  max_messages: number;
  max_message_chars: number;
  /** The most characters the messages of one request may add up to. */
  max_history_chars: number;
  daily_message_limit: number;
  messages_used_today: number;
};

/** One turn of the conversation as the server takes it. The browser keeps the history. */
export type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

/** The run a conversation is about. */
export type ChatRun = { id: string; name: string };

/** A docs section an answer is based on; `index` is the `[n]` of the text, from 1. `url` is a path within the docs, not a full address. */
export type ChatCitation = {
  index: number;
  title: string;
  heading_path: string;
  url: string;
};

export type ChatErrorCode = "model_unavailable" | "timeout" | "internal";
export type ChatFinishReason = "stop" | "length" | "tool_limit";

/**
 * What a streamed reply is made of: the server's events by name, with their data. `interrupted`
 * is the client's own: the stream ended without `done` or `error`.
 */
export type ChatStreamEvent =
  | { type: "text_delta"; text: string }
  | { type: "tool_call"; name: string; label: string }
  | { type: "tool_result_summary"; name: string; ok: boolean }
  | ({ type: "citation" } & ChatCitation)
  | { type: "usage"; input_tokens: number; output_tokens: number }
  | { type: "error"; code: ChatErrorCode; message: string }
  | { type: "done"; finish_reason: ChatFinishReason }
  | { type: "interrupted" };
