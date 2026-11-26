import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { chatStorageKey, loadStoredChat, saveStoredChat } from "../../chat/storage";
import { clearSession, getSignedInAccessToken, startSession } from "../session";

// sessionStorage and localStorage in memory, as the tests run without a browser.
function memoryStorage(): Storage {
  const items = new Map<string, string>();

  return {
    get length() {
      return items.size;
    },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => [...items.keys()][index] ?? null,
    removeItem: (key) => void items.delete(key),
    setItem: (key, value) => void items.set(key, value),
  };
}

const tokens = {
  access_token: "access",
  refresh_token: "refresh",
  expires_in: 300,
  refresh_expires_in: 1800,
  token_type: "Bearer",
};

const chat = {
  run: null,
  messages: [
    {
      id: "u-1",
      role: "user" as const,
      text: "Why did this run fail?",
      status: "complete" as const,
      tools: [],
      citations: [],
      note: null,
    },
  ],
};

beforeEach(() => {
  vi.stubGlobal("window", {
    sessionStorage: memoryStorage(),
    localStorage: memoryStorage(),
    addEventListener: () => {},
    removeEventListener: () => {},
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("clearSession", () => {
  it("removes the chat this tab keeps along with the tokens", () => {
    startSession(tokens as never, false);
    saveStoredChat("user-a", chat);
    saveStoredChat("user-b", chat);
    window.sessionStorage.setItem("other.key", "kept");

    clearSession();

    expect(getSignedInAccessToken()).toBeNull();
    expect(loadStoredChat("user-a")).toBeNull();
    expect(window.sessionStorage.getItem(chatStorageKey("user-b"))).toBeNull();
    expect(window.sessionStorage.getItem("other.key")).toBe("kept");
  });

  it("leaves no chat behind for the next user who signs in", () => {
    saveStoredChat("user-a", chat);

    startSession(tokens as never, true);

    expect(window.sessionStorage.getItem(chatStorageKey("user-a"))).toBeNull();
    expect(getSignedInAccessToken()).toBe("access");
  });
});
