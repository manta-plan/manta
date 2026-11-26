import { isObject } from "../../utils/jsonObject";
import type { ChatMessage, ChatMessageStatus, ChatToolStep } from "./conversation";
import type { ChatCitation, ChatRun } from "./types";

// The server keeps no conversation, so the browser does: in sessionStorage, which belongs to one
// tab and goes when the tab closes. One entry per signed-in user, so that another user in the
// same tab never reads it. Storage can be blocked, full, or hold anything: every read and write
// may fail, and the chat then just works without it.

const keyPrefix = "manta.chat.";
// Raised when the stored shape changes; an entry of another version is discarded.
const storedVersion = 1;

/** The note of a reply that was still being written when its page went away. */
export const interruptedNote = "The answer was interrupted before it finished.";

/** How long a conversation is kept after its last change. */
export const chatRetentionMs = 2 * 60 * 60 * 1000;

/** The visible conversation: its messages and the run it is about. */
export type ChatSnapshot = {
  messages: ChatMessage[];
  run: ChatRun | null;
};

export type RestoredChat = ChatSnapshot & {
  /** When it was last changed, in ms since the epoch; it expires `chatRetentionMs` later. */
  savedAt: number;
};

type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status: ChatMessageStatus;
  tools: { label: string; state: ChatToolStep["state"] }[];
  citations: ChatCitation[];
  note: string | null;
};

type StoredChat = {
  version: typeof storedVersion;
  savedAt: number;
  run: ChatRun | null;
  messages: StoredMessage[];
};

const messageStatuses: readonly string[] = [
  "streaming",
  "complete",
  "stopped",
  "interrupted",
  "error",
];
const toolStates: readonly string[] = ["running", "done", "failed"];

export function chatStorageKey(userId: string) {
  return `${keyPrefix}${userId}`;
}

// Reading the property itself throws where storage is blocked.
function sessionStore(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Keeps the conversation of `userId` and resolves to when it was saved, or null when it could not
 * be kept. An empty conversation is not kept: its entry is removed. A reply still being written
 * is stored as such, and read back as interrupted.
 */
export function saveStoredChat(
  userId: string,
  chat: ChatSnapshot,
  now: number = Date.now(),
): number | null {
  if (chat.messages.length === 0) {
    removeStoredChat(userId);
    return null;
  }

  const stored: StoredChat = {
    version: storedVersion,
    savedAt: now,
    run: chat.run === null ? null : { id: chat.run.id, name: chat.run.name },
    messages: chat.messages.map((message) => ({
      id: message.id,
      role: message.role,
      text: message.text,
      status: message.status,
      tools: message.tools.map((tool) => ({ label: tool.label, state: tool.state })),
      citations: message.citations,
      note: message.note,
    })),
  };

  try {
    const store = sessionStore();

    if (store === null) {
      return null;
    }

    store.setItem(chatStorageKey(userId), JSON.stringify(stored));
    return now;
  } catch {
    // Full or blocked: the conversation stays on screen only.
    return null;
  }
}

/**
 * The conversation kept for `userId`, or null when there is none. An entry that is older than
 * `chatRetentionMs`, unreadable or not in the current shape is removed and counts as none.
 */
export function loadStoredChat(userId: string, now: number = Date.now()): RestoredChat | null {
  let raw: string | null;

  try {
    raw = sessionStore()?.getItem(chatStorageKey(userId)) ?? null;
  } catch {
    return null;
  }

  if (raw === null) {
    return null;
  }

  const chat = parseStoredChat(raw);

  // A time further than the retention from now, in either direction, is not one to trust.
  if (chat === null || Math.abs(now - chat.savedAt) >= chatRetentionMs) {
    removeStoredChat(userId);
    return null;
  }

  return chat;
}

export function removeStoredChat(userId: string) {
  try {
    sessionStore()?.removeItem(chatStorageKey(userId));
  } catch {
    // Nothing was reachable to remove.
  }
}

/** Removes the conversations of every user from this tab. Called when a session ends. */
export function clearStoredChats() {
  try {
    const store = sessionStore();

    if (store === null) {
      return;
    }

    const keys = Array.from({ length: store.length }, (_, index) => store.key(index));

    for (const key of keys) {
      if (key?.startsWith(keyPrefix)) {
        store.removeItem(key);
      }
    }
  } catch {
    // Nothing was reachable to remove.
  }
}

function parseStoredChat(raw: string): RestoredChat | null {
  let stored: unknown;

  try {
    stored = JSON.parse(raw);
  } catch {
    return null;
  }

  if (
    !isObject(stored) ||
    stored.version !== storedVersion ||
    typeof stored.savedAt !== "number" ||
    !Number.isFinite(stored.savedAt) ||
    !Array.isArray(stored.messages) ||
    stored.messages.length === 0
  ) {
    return null;
  }

  const run = stored.run === null ? null : parseRun(stored.run);
  const messages = stored.messages.map(parseMessage);

  if (run === undefined || messages.includes(null)) {
    return null;
  }

  return { savedAt: stored.savedAt, run, messages: messages as ChatMessage[] };
}

function parseRun(value: unknown): ChatRun | undefined {
  return isObject(value) && typeof value.id === "string" && typeof value.name === "string"
    ? { id: value.id, name: value.name }
    : undefined;
}

function parseMessage(value: unknown): ChatMessage | null {
  if (
    !isObject(value) ||
    typeof value.id !== "string" ||
    (value.role !== "user" && value.role !== "assistant") ||
    typeof value.text !== "string" ||
    typeof value.status !== "string" ||
    !messageStatuses.includes(value.status) ||
    !Array.isArray(value.tools) ||
    !Array.isArray(value.citations) ||
    (value.note !== null && typeof value.note !== "string")
  ) {
    return null;
  }

  const tools = value.tools.map(parseTool);
  const citations = value.citations.map(parseCitation);

  if (tools.includes(null) || citations.includes(null)) {
    return null;
  }

  const message: ChatMessage = {
    id: value.id,
    role: value.role,
    text: value.text,
    status: value.status as ChatMessageStatus,
    tools: tools as ChatToolStep[],
    citations: citations as ChatCitation[],
    note: value.note,
  };

  // Its page went away while it was written: what is there is not the whole answer.
  return message.status === "streaming"
    ? { ...message, status: "interrupted", note: interruptedNote }
    : message;
}

function parseTool(value: unknown): ChatToolStep | null {
  return isObject(value) &&
    typeof value.label === "string" &&
    typeof value.state === "string" &&
    toolStates.includes(value.state)
    ? { name: "", label: value.label, state: value.state as ChatToolStep["state"] }
    : null;
}

function parseCitation(value: unknown): ChatCitation | null {
  return isObject(value) &&
    typeof value.index === "number" &&
    typeof value.title === "string" &&
    typeof value.heading_path === "string" &&
    typeof value.url === "string"
    ? { index: value.index, title: value.title, heading_path: value.heading_path, url: value.url }
    : null;
}
