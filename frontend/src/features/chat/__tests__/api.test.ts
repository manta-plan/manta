import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, postStream } from "../../../api/manta";
import {
  fitHistory,
  streamChatReply,
  type ChatReplyEvent,
  type ChatStatus,
  type ChatTurn,
} from "../api";

vi.mock("../../../api/manta", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/manta")>()),
  postStream: vi.fn(),
}));

const mockedPostStream = vi.mocked(postStream);

beforeEach(() => {
  vi.resetAllMocks();
});

const question: ChatTurn[] = [{ role: "user", content: "How do I start a run?" }];

async function replyTo(body: string) {
  mockedPostStream.mockResolvedValue(new Response(body));
  const events: ChatReplyEvent[] = [];
  for await (const event of streamChatReply(question, new AbortController().signal)) {
    events.push(event);
  }
  return events;
}

describe("streamChatReply", () => {
  it("posts the turns and yields the reply's text, then how it ended", async () => {
    const events = await replyTo(
      'event: delta\ndata: {"text": "Click "}\n\nevent: delta\ndata: {"text": "Run."}\n\nevent: done\ndata: {"finish_reason": "stop"}\n\n',
    );

    expect(mockedPostStream).toHaveBeenCalledWith(
      "/v1/chat/messages",
      { messages: question },
      expect.any(AbortSignal),
    );
    expect(events).toEqual([
      { type: "delta", text: "Click " },
      { type: "delta", text: "Run." },
      { type: "done", finishReason: "stop" },
    ]);
  });

  it("reports a reply cut off at the output limit", async () => {
    const events = await replyTo('event: done\ndata: {"finish_reason": "length"}\n\n');

    expect(events).toEqual([{ type: "done", finishReason: "length" }]);
  });

  it("ends with the server's message when the model fails part-way", async () => {
    const events = await replyTo(
      'event: delta\ndata: {"text": "Click"}\n\nevent: error\ndata: {"code": "timeout", "message": "The model took too long to answer. Try again."}\n\n',
    );

    expect(events.at(-1)).toEqual({
      type: "error",
      message: "The model took too long to answer. Try again.",
    });
  });

  it("reports a stream that ends without done or error as interrupted", async () => {
    const events = await replyTo('event: delta\ndata: {"text": "Click"}\n\n');

    expect(events).toEqual([
      { type: "delta", text: "Click" },
      { type: "error", message: "The reply was interrupted. Try again." },
    ]);
  });

  it("throws the ApiError of a request refused before the reply starts", async () => {
    const busy = new ApiError(429, "Rai is busy answering other questions.");
    mockedPostStream.mockRejectedValue(busy);

    await expect(streamChatReply(question, new AbortController().signal).next()).rejects.toBe(busy);
  });
});

describe("fitHistory", () => {
  const limits: ChatStatus = {
    enabled: true,
    max_messages: 3,
    max_message_chars: 10,
    max_history_chars: 20,
  };
  const turn = (role: ChatTurn["role"], content: string): ChatTurn => ({ role, content });

  it("keeps a conversation within the limits as it is", () => {
    const turns = [turn("user", "one"), turn("assistant", "two"), turn("user", "three")];

    expect(fitHistory(turns, limits)).toEqual(turns);
  });

  it("leaves out the oldest turns beyond the message limit, starting with a question", () => {
    const turns = [
      turn("user", "one"),
      turn("assistant", "two"),
      turn("user", "three"),
      turn("assistant", "four"),
      turn("user", "five"),
    ];

    expect(fitHistory(turns, limits)).toEqual(turns.slice(2));
  });

  it("leaves out a reply that would come first", () => {
    const turns = [
      turn("user", "one"),
      turn("assistant", "two"),
      turn("user", "three"),
      turn("user", "four"),
    ];

    expect(fitHistory(turns, limits)).toEqual([turn("user", "three"), turn("user", "four")]);
  });

  it("leaves out the oldest turns beyond the total size limit", () => {
    const turns = [
      turn("user", "123456789"),
      turn("assistant", "123456789"),
      turn("user", "12345"),
    ];

    expect(fitHistory(turns, limits)).toEqual([turn("user", "12345")]);
  });

  it("shortens a turn longer than the message limit", () => {
    expect(
      fitHistory(
        [turn("user", "one"), turn("assistant", "x".repeat(15)), turn("user", "two")],
        limits,
      ),
    ).toEqual([turn("user", "one"), turn("assistant", "x".repeat(10)), turn("user", "two")]);
  });

  it("always keeps the question itself", () => {
    expect(fitHistory([turn("user", "one")], { ...limits, max_messages: 0 })).toEqual([
      turn("user", "one"),
    ]);
  });
});
