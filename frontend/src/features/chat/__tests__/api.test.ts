import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getJson, postStream } from "../../../api/manta";
import { getChatStatus, streamChatReply, toChatStreamEvent } from "../api";
import type { ChatHistoryMessage, ChatStreamEvent } from "../types";

vi.mock("../../../api/manta", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/manta")>()),
  getJson: vi.fn(),
  postStream: vi.fn(),
}));

const mockedGetJson = vi.mocked(getJson);
const mockedPostStream = vi.mocked(postStream);

beforeEach(() => {
  vi.resetAllMocks();
});

const encoder = new TextEncoder();

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function streamResponse(...chunks: string[]) {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }),
  );
}

const question: ChatHistoryMessage[] = [{ role: "user", content: "Why?" }];

async function collect(signal = new AbortController().signal) {
  const events: ChatStreamEvent[] = [];

  for await (const event of streamChatReply(question, null, signal)) {
    events.push(event);
  }

  return events;
}

describe("requests", () => {
  it("reads the chat status", async () => {
    const status = {
      enabled: true,
      max_messages: 12,
      max_message_chars: 2000,
      max_history_chars: 6000,
      daily_message_limit: 20,
      messages_used_today: 3,
    };
    mockedGetJson.mockResolvedValue({ ...status, extra: "ignored" });

    await expect(getChatStatus()).resolves.toEqual(status);
    expect(mockedGetJson).toHaveBeenCalledWith("/v1/chat/status");
  });

  it("refuses a status that is not one", async () => {
    mockedGetJson.mockResolvedValue({ enabled: "yes" });

    await expect(getChatStatus()).rejects.toThrow("not in the expected form");
  });
});

describe("streamChatReply", () => {
  it("posts the conversation and the run, and nothing else", async () => {
    mockedPostStream.mockResolvedValue(streamResponse(sse("done", { finish_reason: "stop" })));
    const { signal } = new AbortController();
    const messages: ChatHistoryMessage[] = [
      { role: "user", content: "Why did it fail?" },
      { role: "assistant", content: "It ran out of memory." },
      { role: "user", content: "How do I fix that?" },
    ];
    const events: ChatStreamEvent[] = [];

    for await (const event of streamChatReply(messages, "r1", signal)) {
      events.push(event);
    }

    expect(mockedPostStream).toHaveBeenCalledTimes(1);
    expect(mockedPostStream).toHaveBeenCalledWith(
      "/v1/chat/messages",
      { messages, run_uuid: "r1" },
      signal,
    );
    expect(events).toEqual([{ type: "done", finish_reason: "stop" }]);
  });

  it("maps each event of the contract", async () => {
    mockedPostStream.mockResolvedValue(
      streamResponse(
        sse("tool_call", { name: "get_run_logs", label: "Checking run logs" }),
        sse("tool_result_summary", { name: "get_run_logs", ok: true }),
        sse("text_delta", { text: "The solver " }),
        sse("text_delta", { text: "ran out of memory." }),
        sse("citation", {
          index: 1,
          title: "Run",
          heading_path: "Run > Start a run",
          url: "user-guide/run.md#start-a-run",
        }),
        sse("usage", { input_tokens: 120, output_tokens: 30 }),
        sse("done", { finish_reason: "length" }),
      ),
    );

    expect(await collect()).toEqual([
      { type: "tool_call", name: "get_run_logs", label: "Checking run logs" },
      { type: "tool_result_summary", name: "get_run_logs", ok: true },
      { type: "text_delta", text: "The solver " },
      { type: "text_delta", text: "ran out of memory." },
      {
        type: "citation",
        index: 1,
        title: "Run",
        heading_path: "Run > Start a run",
        url: "user-guide/run.md#start-a-run",
      },
      { type: "usage", input_tokens: 120, output_tokens: 30 },
      { type: "done", finish_reason: "length" },
    ]);
  });

  it("skips unknown events and data that is not what the event promises", async () => {
    mockedPostStream.mockResolvedValue(
      streamResponse(
        sse("ping", {}),
        sse("text_delta", { text: 42 }),
        "event: text_delta\ndata: not json\n\n",
        "event: text_delta\ndata: [1]\n\n",
        sse("tool_call", { name: "get_run", arguments: { run_uuid: "r1" } }),
        sse("text_delta", { text: "ok" }),
        sse("done", { finish_reason: "stop" }),
      ),
    );

    expect(await collect()).toEqual([
      { type: "text_delta", text: "ok" },
      { type: "done", finish_reason: "stop" },
    ]);
  });

  it("stops at an error event", async () => {
    mockedPostStream.mockResolvedValue(
      streamResponse(
        sse("text_delta", { text: "The" }),
        sse("error", { code: "timeout", message: "The model took too long." }),
        sse("text_delta", { text: "late" }),
      ),
    );

    expect(await collect()).toEqual([
      { type: "text_delta", text: "The" },
      { type: "error", code: "timeout", message: "The model took too long." },
    ]);
  });

  it("reads nothing after done", async () => {
    mockedPostStream.mockResolvedValue(
      streamResponse(sse("done", { finish_reason: "stop" }), sse("text_delta", { text: "late" })),
    );

    expect(await collect()).toEqual([{ type: "done", finish_reason: "stop" }]);
  });

  it("counts a stream that ends without done or error as interrupted", async () => {
    mockedPostStream.mockResolvedValue(streamResponse(sse("text_delta", { text: "The" })));

    expect(await collect()).toEqual([{ type: "text_delta", text: "The" }, { type: "interrupted" }]);
  });

  it("counts a connection that drops as interrupted", async () => {
    mockedPostStream.mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          pull(controller) {
            controller.error(new TypeError("network error"));
          },
        }),
      ),
    );

    expect(await collect()).toEqual([{ type: "interrupted" }]);
  });

  it("counts a reply without a body as interrupted", async () => {
    mockedPostStream.mockResolvedValue(new Response(null));

    expect(await collect()).toEqual([{ type: "interrupted" }]);
  });

  it("throws the abort when the reply is stopped while it is read", async () => {
    const controller = new AbortController();
    mockedPostStream.mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(stream) {
            stream.enqueue(encoder.encode(sse("text_delta", { text: "The" })));
            controller.signal.addEventListener("abort", () =>
              stream.error(new DOMException("Aborted", "AbortError")),
            );
          },
        }),
      ),
    );
    const events: ChatStreamEvent[] = [];

    await expect(async () => {
      for await (const event of streamChatReply(question, null, controller.signal)) {
        events.push(event);
        controller.abort();
      }
    }).rejects.toThrow("Aborted");
    expect(events).toEqual([{ type: "text_delta", text: "The" }]);
  });

  it("throws the abort when the request is stopped before the reply starts", async () => {
    mockedPostStream.mockRejectedValue(new DOMException("Aborted", "AbortError"));

    await expect(collect(AbortSignal.abort())).rejects.toThrow("Aborted");
  });

  it.each([
    [404, "Chat is disabled"],
    [422, "Unprocessable Entity"],
    [429, "Too many requests"],
  ])("throws the API error of a %i before the stream starts", async (status, message) => {
    mockedPostStream.mockRejectedValue(
      new ApiError(
        status,
        message,
        status === 429 ? 30 : null,
        status === 429 ? "daily_limit" : null,
      ),
    );

    const failure = await collect().catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      status,
      message,
      retryAfterSeconds: status === 429 ? 30 : null,
      code: status === 429 ? "daily_limit" : null,
    });
  });
});

describe("toChatStreamEvent", () => {
  it("reads a heading path given as a list", () => {
    expect(
      toChatStreamEvent({
        event: "citation",
        data: JSON.stringify({
          index: 2,
          title: "Run",
          heading_path: ["Run", "Start a run"],
          url: "user-guide/run.md#start-a-run",
        }),
      }),
    ).toMatchObject({ heading_path: "Run › Start a run" });
  });

  it("ends the reply on an error or done it does not fully know", () => {
    expect(toChatStreamEvent({ event: "error", data: '{"code":"new_code"}' })).toEqual({
      type: "error",
      code: "internal",
      message: "",
    });
    expect(toChatStreamEvent({ event: "done", data: '{"finish_reason":"cancelled"}' })).toEqual({
      type: "done",
      finish_reason: "stop",
    });
  });
});
