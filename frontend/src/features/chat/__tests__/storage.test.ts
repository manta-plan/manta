import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../conversation";
import {
  chatRetentionMs,
  chatStorageKey,
  clearStoredChats,
  loadStoredChat,
  removeStoredChat,
  saveStoredChat,
  type ChatSnapshot,
} from "../storage";

// A sessionStorage in memory, as the tests run without a browser.
class MemoryStorage implements Storage {
  private items = new Map<string, string>();

  get length() {
    return this.items.size;
  }

  clear() {
    this.items.clear();
  }

  getItem(key: string) {
    return this.items.get(key) ?? null;
  }

  key(index: number) {
    return [...this.items.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.items.delete(key);
  }

  setItem(key: string, value: string) {
    this.items.set(key, value);
  }
}

let sessionStorage: MemoryStorage;
let localStorage: MemoryStorage;

beforeEach(() => {
  sessionStorage = new MemoryStorage();
  localStorage = new MemoryStorage();
  vi.stubGlobal("window", { sessionStorage, localStorage });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const now = Date.parse("2026-11-25T10:00:00Z");

function message(overrides: Partial<ChatMessage> & Pick<ChatMessage, "id" | "role">): ChatMessage {
  return { text: "", status: "complete", tools: [], citations: [], note: null, ...overrides };
}

const chat: ChatSnapshot = {
  run: { id: "r1", name: "Base case 2030" },
  messages: [
    message({ id: "u-1", role: "user", text: "Why did this run fail?" }),
    message({
      id: "a-1",
      role: "assistant",
      text: "It ran out of memory [1].",
      tools: [
        { name: "get_run_logs", label: "Checking run logs", state: "done" },
        { name: "search_docs", label: "Searching the docs", state: "failed" },
      ],
      citations: [
        { index: 1, title: "Run", heading_path: "Run › Logs", url: "user-guide/run.md#logs" },
      ],
      note: "The answer reached the length limit and was cut short.",
    }),
    message({ id: "u-2", role: "user", text: "And then?" }),
    message({ id: "a-2", role: "assistant", text: "The sol", status: "stopped", note: "Stopped." }),
  ],
};

// What comes back: everything shown, with the tools by their labels only.
const restored = {
  ...chat,
  messages: chat.messages.map((item) => ({
    ...item,
    tools: item.tools.map((tool) => ({ ...tool, name: "" })),
  })),
};

function storedEntry(userId = "user-a") {
  return JSON.parse(sessionStorage.getItem(chatStorageKey(userId)) ?? "null") as Record<
    string,
    unknown
  > | null;
}

describe("round trip", () => {
  it("keeps the conversation and reads it back", () => {
    expect(saveStoredChat("user-a", chat, now)).toBe(now);
    expect(loadStoredChat("user-a", now + 1000)).toEqual({ ...restored, savedAt: now });
  });

  it("keeps it in sessionStorage only, under one key with the user's id", () => {
    saveStoredChat("user-a", chat, now);

    expect(chatStorageKey("user-a")).toBe("manta.chat.user-a");
    expect(sessionStorage.length).toBe(1);
    expect(sessionStorage.key(0)).toBe("manta.chat.user-a");
    expect(localStorage.length).toBe(0);
  });

  it("stores no tool names", () => {
    saveStoredChat("user-a", chat, now);

    expect(sessionStorage.getItem(chatStorageKey("user-a"))).not.toContain("get_run_logs");
    expect(sessionStorage.getItem(chatStorageKey("user-a"))).toContain("Checking run logs");
  });

  it("keeps a conversation without a run", () => {
    saveStoredChat("user-a", { ...chat, run: null }, now);

    expect(loadStoredChat("user-a", now)?.run).toBeNull();
  });

  it("has nothing for a user who kept nothing", () => {
    expect(loadStoredChat("user-a", now)).toBeNull();
  });

  it("replaces what was kept before", () => {
    saveStoredChat("user-a", chat, now);
    saveStoredChat("user-a", { run: null, messages: chat.messages.slice(0, 2) }, now + 5);

    expect(loadStoredChat("user-a", now + 5)).toMatchObject({ run: null, savedAt: now + 5 });
    expect(loadStoredChat("user-a", now + 5)?.messages).toHaveLength(2);
  });
});

describe("per user", () => {
  it("never gives one user the conversation of another", () => {
    saveStoredChat("user-a", chat, now);

    expect(loadStoredChat("user-b", now)).toBeNull();
    expect(loadStoredChat("user-a", now)).not.toBeNull();
  });

  it("keeps the conversations of two users apart", () => {
    saveStoredChat("user-a", chat, now);
    saveStoredChat("user-b", { run: null, messages: chat.messages.slice(0, 1) }, now);

    expect(loadStoredChat("user-a", now)?.messages).toHaveLength(4);
    expect(loadStoredChat("user-b", now)?.messages).toHaveLength(1);
  });
});

describe("expiry", () => {
  it("lasts two hours from the last change", () => {
    expect(chatRetentionMs).toBe(2 * 60 * 60 * 1000);
  });

  it("is still there a moment before two hours have passed", () => {
    saveStoredChat("user-a", chat, now);

    expect(loadStoredChat("user-a", now + chatRetentionMs - 1)).not.toBeNull();
    expect(storedEntry()).not.toBeNull();
  });

  it("is gone, and removed, at two hours", () => {
    saveStoredChat("user-a", chat, now);

    expect(loadStoredChat("user-a", now + chatRetentionMs)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("counts from the last change, not the first", () => {
    saveStoredChat("user-a", chat, now);
    saveStoredChat("user-a", chat, now + chatRetentionMs - 1);

    expect(loadStoredChat("user-a", now + chatRetentionMs + 1000)).not.toBeNull();
  });

  it("does not trust a time far in the future", () => {
    saveStoredChat("user-a", chat, now + chatRetentionMs);

    expect(loadStoredChat("user-a", now)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });
});

describe("a reply still being written", () => {
  it("is read back as interrupted, never as finished", () => {
    saveStoredChat(
      "user-a",
      {
        run: null,
        messages: [
          message({ id: "u-1", role: "user", text: "Why?" }),
          message({
            id: "a-1",
            role: "assistant",
            text: "The solv",
            status: "streaming",
            tools: [{ name: "get_run_logs", label: "Checking run logs", state: "running" }],
          }),
        ],
      },
      now,
    );

    expect(storedEntry()?.messages).toMatchObject([{}, { status: "streaming" }]);
    expect(loadStoredChat("user-a", now)?.messages.at(-1)).toMatchObject({
      status: "interrupted",
      text: "The solv",
      note: "The answer was interrupted before it finished.",
    });
  });
});

describe("clearing", () => {
  it("removes the entry when the conversation is emptied", () => {
    saveStoredChat("user-a", chat, now);

    expect(saveStoredChat("user-a", { run: null, messages: [] }, now)).toBeNull();
    expect(sessionStorage.length).toBe(0);
    expect(loadStoredChat("user-a", now)).toBeNull();
  });

  it("does not keep a run without a conversation", () => {
    expect(saveStoredChat("user-a", { run: chat.run, messages: [] }, now)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("removes one user's entry", () => {
    saveStoredChat("user-a", chat, now);
    saveStoredChat("user-b", chat, now);
    removeStoredChat("user-a");

    expect(loadStoredChat("user-a", now)).toBeNull();
    expect(loadStoredChat("user-b", now)).not.toBeNull();
  });

  it("removes every user's entry and nothing else when a session ends", () => {
    saveStoredChat("user-a", chat, now);
    saveStoredChat("user-b", chat, now);
    sessionStorage.setItem("manta.session", "kept");
    clearStoredChats();

    expect(sessionStorage.length).toBe(1);
    expect(sessionStorage.getItem("manta.session")).toBe("kept");
  });
});

describe("data that cannot be used", () => {
  function storeRaw(raw: string) {
    sessionStorage.setItem(chatStorageKey("user-a"), raw);
  }

  // A valid entry, changed.
  function storeChanged(change: (entry: Record<string, unknown>) => void) {
    saveStoredChat("user-a", chat, now);
    const entry = storedEntry()!;
    change(entry);
    storeRaw(JSON.stringify(entry));
  }

  const reply = (entry: Record<string, unknown>) =>
    (entry.messages as Record<string, unknown>[])[1];

  it.each([
    ["text that is not JSON", "{not json"],
    ["an empty string", ""],
    ["a list", "[]"],
    ["null", "null"],
    ["a number", "42"],
    ["an object of another kind", '{"hello":"world"}'],
  ])("discards %s", (_case, raw) => {
    storeRaw(raw);

    expect(loadStoredChat("user-a", now)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it.each<[string, (entry: Record<string, unknown>) => void]>([
    ["another version", (entry) => (entry.version = 0)],
    ["no version", (entry) => delete entry.version],
    ["no time", (entry) => delete entry.savedAt],
    ["a time that is text", (entry) => (entry.savedAt = "2026-11-25")],
    ["messages that are not a list", (entry) => (entry.messages = {})],
    ["no messages", (entry) => (entry.messages = [])],
    ["a run without a name", (entry) => (entry.run = { id: "r1" })],
    ["a run that is text", (entry) => (entry.run = "r1")],
    ["a message that is not an object", (entry) => (entry.messages = ["hello"])],
    ["a role the chat does not have", (entry) => (reply(entry).role = "system")],
    ["a status the chat does not have", (entry) => (reply(entry).status = "cancelled")],
    ["the server's field names", (entry) => (entry.messages = [{ role: "user", content: "Hi" }])],
    ["text that is not text", (entry) => (reply(entry).text = 42)],
    ["a note that is not text", (entry) => (reply(entry).note = 1)],
    ["a tool without a label", (entry) => (reply(entry).tools = [{ state: "done" }])],
    [
      "a tool in an unknown state",
      (entry) => (reply(entry).tools = [{ label: "Checking", state: "queued" }]),
    ],
    ["a citation without an index", (entry) => (reply(entry).citations = [{ title: "Run" }])],
    ["no citations", (entry) => delete reply(entry).citations],
  ])("discards an entry with %s", (_case, change) => {
    storeChanged(change);

    expect(loadStoredChat("user-a", now)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("ignores fields it does not know", () => {
    storeChanged((entry) => {
      entry.extra = true;
      reply(entry).html = "<b>no</b>";
    });

    expect(loadStoredChat("user-a", now)).toEqual({ ...restored, savedAt: now });
  });
});

describe("storage that fails", () => {
  const failing = (name: string) => () => {
    throw new DOMException(name, name);
  };

  it("works without any storage", () => {
    vi.stubGlobal("window", {
      get sessionStorage(): Storage {
        throw new DOMException("The operation is insecure.", "SecurityError");
      },
    });

    expect(saveStoredChat("user-a", chat, now)).toBeNull();
    expect(loadStoredChat("user-a", now)).toBeNull();
    expect(() => removeStoredChat("user-a")).not.toThrow();
    expect(() => clearStoredChats()).not.toThrow();
  });

  it("carries on when the storage is full", () => {
    sessionStorage.setItem = failing("QuotaExceededError");

    expect(saveStoredChat("user-a", chat, now)).toBeNull();
    expect(loadStoredChat("user-a", now)).toBeNull();
  });

  it("carries on when reading and removing throw", () => {
    saveStoredChat("user-a", chat, now);
    sessionStorage.getItem = failing("SecurityError");
    sessionStorage.removeItem = failing("SecurityError");
    sessionStorage.key = failing("SecurityError");

    expect(loadStoredChat("user-a", now)).toBeNull();
    expect(() => removeStoredChat("user-a")).not.toThrow();
    expect(() => clearStoredChats()).not.toThrow();
    expect(() => saveStoredChat("user-a", { run: null, messages: [] }, now)).not.toThrow();
  });

  it("carries on when an unusable entry cannot be removed", () => {
    sessionStorage.setItem(chatStorageKey("user-a"), "{not json");
    sessionStorage.removeItem = failing("SecurityError");

    expect(loadStoredChat("user-a", now)).toBeNull();
  });
});
