import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/manta";
import { streamChatReply } from "../api";
import {
  buildHistory,
  chatReducer,
  initialChatState,
  questionsLeft,
  runChatTurn,
  type ChatAction,
  type ChatMessage,
  type ChatState,
} from "../conversation";
import type { ChatHistoryMessage, ChatStatus, ChatStreamEvent } from "../types";

vi.mock("../api", () => ({
  streamChatReply: vi.fn(),
}));

const mockedStreamChatReply = vi.mocked(streamChatReply);

beforeEach(() => {
  vi.resetAllMocks();
});

const status: ChatStatus = {
  enabled: true,
  max_messages: 12,
  max_message_chars: 2000,
  max_history_chars: 6000,
  daily_message_limit: 20,
  messages_used_today: 3,
};

function reduce(state: ChatState, ...actions: ChatAction[]) {
  return actions.reduce(chatReducer, state);
}

function events(...list: ChatStreamEvent[]): ChatAction[] {
  return list.map((event) => ({ type: "event", event }));
}

const asked = reduce(initialChatState, {
  type: "send",
  userId: "u-0",
  assistantId: "a-0",
  text: "Why did this run fail?",
});

describe("chatReducer", () => {
  it("opens a reply when a question is sent", () => {
    expect(asked.isStreaming).toBe(true);
    expect(asked.messages).toMatchObject([
      { id: "u-0", role: "user", text: "Why did this run fail?", status: "complete" },
      { id: "a-0", role: "assistant", text: "", status: "streaming" },
    ]);
  });

  it("does not take a second question while a reply is open", () => {
    expect(reduce(asked, { type: "send", userId: "u-1", assistantId: "a-1", text: "And?" })).toBe(
      asked,
    );
  });

  it("builds the reply from the stream", () => {
    const state = reduce(
      asked,
      ...events(
        { type: "tool_call", name: "get_run_logs", label: "Checking run logs" },
        { type: "tool_call", name: "search_docs", label: "Searching the docs" },
        { type: "tool_result_summary", name: "get_run_logs", ok: false },
        { type: "tool_result_summary", name: "search_docs", ok: true },
        { type: "text_delta", text: "The solver " },
        { type: "text_delta", text: "ran out of memory." },
        { type: "citation", index: 2, title: "Run", heading_path: "Logs", url: "run.md#logs" },
        { type: "citation", index: 1, title: "Run", heading_path: "Start", url: "run.md#start" },
        { type: "citation", index: 1, title: "Run", heading_path: "Start", url: "run.md#start" },
        { type: "usage", input_tokens: 10, output_tokens: 5 },
      ),
    );

    expect(state.isStreaming).toBe(true);
    expect(state.messages.at(-1)).toEqual({
      id: "a-0",
      role: "assistant",
      text: "The solver ran out of memory.",
      status: "streaming",
      tools: [
        { name: "get_run_logs", label: "Checking run logs", state: "failed" },
        { name: "search_docs", label: "Searching the docs", state: "done" },
      ],
      citations: [
        { index: 1, title: "Run", heading_path: "Start", url: "run.md#start" },
        { index: 2, title: "Run", heading_path: "Logs", url: "run.md#logs" },
      ],
      note: null,
    });
  });

  it("closes the reply on done", () => {
    const state = reduce(
      asked,
      ...events({ type: "text_delta", text: "Done." }, { type: "done", finish_reason: "stop" }),
    );

    expect(state.isStreaming).toBe(false);
    expect(state.messages.at(-1)).toMatchObject({ status: "complete", text: "Done.", note: null });
  });

  it.each([
    ["length", "complete", "length limit"],
    ["tool_limit", "complete", "limit of lookups"],
  ] as const)("says why a reply ended with %s", (finish_reason, expectedStatus, note) => {
    const state = reduce(asked, ...events({ type: "done", finish_reason }));

    expect(state.isStreaming).toBe(false);
    expect(state.messages.at(-1)?.status).toBe(expectedStatus);
    expect(state.messages.at(-1)?.note).toContain(note);
  });

  it("keeps what was written when the reply is stopped", () => {
    const state = reduce(asked, ...events({ type: "text_delta", text: "The sol" }), {
      type: "stopped",
    });

    expect(state.isStreaming).toBe(false);
    expect(state.messages.at(-1)).toMatchObject({
      status: "stopped",
      text: "The sol",
      note: "Stopped.",
    });
  });

  it.each([
    ["model_unavailable", "not available"],
    ["timeout", "took too long"],
    ["internal", "went wrong"],
  ] as const)("explains a %s error in its own words", (code, note) => {
    const state = reduce(
      asked,
      ...events({ type: "error", code, message: "Traceback (most recent call last)" }),
    );

    expect(state.messages.at(-1)?.status).toBe("error");
    expect(state.messages.at(-1)?.note).toContain(note);
    expect(state.messages.at(-1)?.note).not.toContain("Traceback");
  });

  it("marks an interrupted reply", () => {
    const state = reduce(
      asked,
      ...events({ type: "text_delta", text: "The" }, { type: "interrupted" }),
    );

    expect(state.isStreaming).toBe(false);
    expect(state.messages.at(-1)).toMatchObject({ status: "interrupted", text: "The" });
  });

  it("ignores what arrives after the reply has closed", () => {
    const closed = reduce(asked, { type: "stopped" });

    expect(
      reduce(closed, ...events({ type: "text_delta", text: "late" }), {
        type: "failed",
        note: "late",
      }),
    ).toBe(closed);
  });

  it("asks again in place of a failed reply", () => {
    const failed = reduce(asked, { type: "failed", note: "Rai could not answer. Try again." });
    const retried = reduce(failed, { type: "retry", assistantId: "a-1" });

    expect(retried.isStreaming).toBe(true);
    expect(retried.messages.map((message) => message.id)).toEqual(["u-0", "a-1"]);
    expect(retried.messages.at(-1)).toMatchObject({ status: "streaming", text: "", note: null });
  });

  it("does not ask again after a reply that ended well or was stopped", () => {
    const complete = reduce(asked, ...events({ type: "done", finish_reason: "stop" }));
    const stopped = reduce(asked, { type: "stopped" });

    expect(reduce(complete, { type: "retry", assistantId: "a-1" })).toBe(complete);
    expect(reduce(stopped, { type: "retry", assistantId: "a-1" })).toBe(stopped);
    expect(reduce(initialChatState, { type: "retry", assistantId: "a-1" })).toBe(initialChatState);
  });

  it("empties the conversation on clear, also while a reply is written", () => {
    const answered = reduce(asked, ...events({ type: "done", finish_reason: "stop" }));

    expect(reduce(answered, { type: "clear" })).toEqual({ messages: [], isStreaming: false });
    expect(reduce(asked, { type: "clear" })).toEqual({ messages: [], isStreaming: false });
    // What the stopped request still reports changes nothing.
    expect(
      reduce(asked, { type: "clear" }, { type: "stopped" }, ...events({ type: "interrupted" })),
    ).toEqual({ messages: [], isStreaming: false });
  });
});

describe("questionsLeft", () => {
  it("counts down to zero, and is null without a daily limit", () => {
    expect(questionsLeft(status)).toBe(17);
    expect(questionsLeft({ ...status, messages_used_today: 20 })).toBe(0);
    expect(questionsLeft({ ...status, messages_used_today: 25 })).toBe(0);
    expect(questionsLeft({ ...status, daily_message_limit: 0 })).toBeNull();
  });
});

describe("buildHistory", () => {
  const limits = { max_messages: 12, max_message_chars: 2000, max_history_chars: 6000 };

  function message(
    role: ChatMessage["role"],
    text: string,
    overrides: Partial<ChatMessage> = {},
  ): ChatMessage {
    return {
      id: `${role}-${text}`,
      role,
      text,
      status: "complete",
      tools: [],
      citations: [],
      note: null,
      ...overrides,
    };
  }

  // Exchanges q1/a1 … qn/an.
  function exchanges(count: number) {
    return Array.from({ length: count }, (_, index) => [
      message("user", `q${index + 1}`),
      message("assistant", `a${index + 1}`),
    ]).flat();
  }

  it("sends only the question when nothing came before", () => {
    expect(buildHistory([], "Why?", limits)).toEqual([{ role: "user", content: "Why?" }]);
  });

  it("sends the exchanges so far as role and text only, then the question", () => {
    const previous = [
      message("user", "Why did it fail?"),
      message("assistant", "\n\nOut of memory [1].\n", {
        tools: [{ name: "get_run_logs", label: "Checking run logs", state: "done" }],
        citations: [{ index: 1, title: "Run", heading_path: "Logs", url: "run.md#logs" }],
        note: "The answer reached the length limit and was cut short.",
      }),
    ];

    expect(buildHistory(previous, "How do I fix it?", limits)).toEqual([
      { role: "user", content: "Why did it fail?" },
      { role: "assistant", content: "Out of memory [1]." },
      { role: "user", content: "How do I fix it?" },
    ]);
  });

  it("leaves out an exchange whose reply failed, was interrupted, is open or has no text", () => {
    const previous = [
      message("user", "q-error"),
      message("assistant", "Half an", { status: "error", note: "Something went wrong." }),
      message("user", "q-interrupted"),
      message("assistant", "Half an", { status: "interrupted", note: "Interrupted." }),
      message("user", "q-open"),
      message("assistant", "Half an", { status: "streaming" }),
      message("user", "q-empty"),
      message("assistant", "  \n", { status: "complete" }),
      message("user", "q-stopped-empty"),
      message("assistant", "", { status: "stopped", note: "Stopped." }),
      message("user", "q-ok"),
      message("assistant", "a-ok"),
    ];

    expect(buildHistory(previous, "next", limits)).toEqual([
      { role: "user", content: "q-ok" },
      { role: "assistant", content: "a-ok" },
      { role: "user", content: "next" },
    ]);
  });

  it("sends a stopped reply that has text, without its note", () => {
    const previous = [
      message("user", "q1"),
      message("assistant", "The sol", { status: "stopped", note: "Stopped." }),
    ];

    expect(buildHistory(previous, "go on", limits)).toEqual([
      { role: "user", content: "q1" },
      { role: "assistant", content: "The sol" },
      { role: "user", content: "go on" },
    ]);
  });

  it("drops the oldest exchanges to fit max_messages, and ends on the question", () => {
    const history = buildHistory(exchanges(10), "next", { ...limits, max_messages: 6 });

    // Five would fit by count, but an exchange is kept whole.
    expect(history.map((item) => item.content)).toEqual(["q9", "a9", "q10", "a10", "next"]);
    expect(history.at(-1)).toEqual({ role: "user", content: "next" });
    expect(buildHistory(exchanges(10), "next", { ...limits, max_messages: 5 })).toHaveLength(5);
    expect(buildHistory(exchanges(10), "next", limits)).toHaveLength(11);
  });

  it("drops the oldest exchanges to fit max_history_chars, without cutting text", () => {
    const previous = [
      message("user", "a".repeat(40)),
      message("assistant", "b".repeat(40)),
      message("user", "c".repeat(30)),
      message("assistant", "d".repeat(30)),
    ];
    const question = "e".repeat(10);

    // 10 + 60 fits in 70; the older 80 does not fit on top.
    expect(
      buildHistory(previous, question, { ...limits, max_history_chars: 70 }).map(
        (item) => item.content.length,
      ),
    ).toEqual([30, 30, 10]);
    expect(buildHistory(previous, question, { ...limits, max_history_chars: 69 })).toEqual([
      { role: "user", content: question },
    ]);
    expect(buildHistory(previous, question, { ...limits, max_history_chars: 150 })).toHaveLength(5);
  });

  it("ends the history at a message longer than max_message_chars", () => {
    const previous = [
      message("user", "q1"),
      message("assistant", "a1"),
      message("user", "q2"),
      message("assistant", "x".repeat(11)),
      message("user", "q3"),
      message("assistant", "a3"),
    ];

    expect(
      buildHistory(previous, "next", { ...limits, max_message_chars: 10 }).map(
        (item) => item.content,
      ),
    ).toEqual(["q3", "a3", "next"]);
  });

  it("always sends the question, even when the limits leave room for nothing", () => {
    expect(
      buildHistory(exchanges(2), "next", {
        max_messages: 0,
        max_message_chars: 1,
        max_history_chars: 0,
      }),
    ).toEqual([{ role: "user", content: "next" }]);
  });
});

describe("runChatTurn", () => {
  const messages: ChatHistoryMessage[] = [{ role: "user", content: "Why did this run fail?" }];

  // The turn of a question already sent, as the view runs it.
  function startTurn(
    turn: { runUuid?: string | null; signal?: AbortSignal } = {},
    refreshStatus = vi.fn(async (): Promise<unknown> => undefined),
  ) {
    let state = asked;
    const done = runChatTurn(
      {
        messages,
        runUuid: turn.runUuid ?? null,
        signal: turn.signal ?? new AbortController().signal,
      },
      (action) => {
        state = chatReducer(state, action);
      },
      refreshStatus,
    );

    return { done, state: () => state, refreshStatus };
  }

  // A reply that fails before the stream starts.
  function failWith(error: unknown) {
    mockedStreamChatReply.mockImplementation(async function* () {
      yield* [];
      throw error;
    });
  }

  it("streams the reply and reads the status again", async () => {
    mockedStreamChatReply.mockImplementation(async function* () {
      yield { type: "text_delta", text: "Out of " };
      yield { type: "text_delta", text: "memory." };
      yield { type: "done", finish_reason: "stop" };
    });
    const signal = new AbortController().signal;
    const turn = startTurn({ runUuid: "r1", signal });

    await turn.done;
    expect(mockedStreamChatReply).toHaveBeenCalledWith(messages, "r1", signal);
    expect(turn.state().isStreaming).toBe(false);
    expect(turn.state().messages.at(-1)).toMatchObject({
      status: "complete",
      text: "Out of memory.",
    });
    expect(turn.refreshStatus).toHaveBeenCalledTimes(1);
  });

  it("marks the reply as stopped itself when the request is aborted", async () => {
    const controller = new AbortController();
    mockedStreamChatReply.mockImplementation(async function* () {
      yield { type: "text_delta", text: "The sol" };
      await new Promise((_resolve, reject) => {
        controller.signal.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      });
    });
    const turn = startTurn({ signal: controller.signal });

    await vi.waitFor(() => expect(turn.state().messages.at(-1)?.text).toBe("The sol"));
    expect(turn.state().isStreaming).toBe(true);
    controller.abort();

    await turn.done;
    expect(turn.state().isStreaming).toBe(false);
    expect(turn.state().messages.at(-1)).toMatchObject({
      status: "stopped",
      text: "The sol",
      note: "Stopped.",
    });
    expect(turn.refreshStatus).toHaveBeenCalledTimes(1);
  });

  it("says the daily limit is used up on a 429 with the code daily_limit", async () => {
    failWith(new ApiError(429, "Daily limit reached", 3600, "daily_limit"));
    const turn = startTurn();

    await turn.done;
    expect(turn.state().messages.at(-1)).toMatchObject({
      status: "error",
      note: "You have used all of today's questions. Try again tomorrow.",
    });
    expect(turn.refreshStatus).toHaveBeenCalledTimes(1);
  });

  it("says the server is busy on a 429 with the code concurrency_limit", async () => {
    failWith(new ApiError(429, "Too many requests", 30, "concurrency_limit"));
    const turn = startTurn();

    await turn.done;
    expect(turn.state().messages.at(-1)).toMatchObject({
      status: "error",
      note: "Rai is busy answering other questions. Try again in 30 seconds.",
    });
  });

  it.each([
    [new ApiError(429, "Too many requests", 1, "concurrency_limit"), "Try again in 1 second."],
    [
      new ApiError(429, "Too many requests"),
      "Rai is busy answering other questions. Try again in a moment.",
    ],
    [new ApiError(404, "Not Found"), "Chat is not available right now."],
    [new ApiError(422, "Unprocessable Entity"), "Rai could not accept that message."],
    [new ApiError(500, "Internal Server Error"), "Rai could not answer. Try again."],
    [new TypeError("Failed to fetch"), "Check your connection"],
  ])("fails the reply with words the user can act on: %s", async (error, note) => {
    failWith(error);
    const turn = startTurn();

    await turn.done;
    expect(turn.state().isStreaming).toBe(false);
    expect(turn.state().messages.at(-1)?.status).toBe("error");
    expect(turn.state().messages.at(-1)?.note).toContain(note);
  });

  it("does not fail when the status cannot be read again", async () => {
    mockedStreamChatReply.mockImplementation(async function* () {
      yield { type: "done", finish_reason: "stop" };
    });
    const turn = startTurn(
      {},
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );

    await expect(turn.done).resolves.toBeUndefined();
    expect(turn.state().messages.at(-1)?.status).toBe("complete");
  });
});
