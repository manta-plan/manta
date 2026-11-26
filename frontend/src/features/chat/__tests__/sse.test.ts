import { describe, expect, it } from "vitest";
import { readSseEvents, type SseEvent } from "../sse";

const encoder = new TextEncoder();

function streamOf(...chunks: (string | Uint8Array)[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }

      controller.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>) {
  const events: SseEvent[] = [];

  for await (const event of readSseEvents(body)) {
    events.push(event);
  }

  return events;
}

describe("readSseEvents", () => {
  it("reads several events from one chunk", async () => {
    const events = await collect(
      streamOf('event: text_delta\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\n'),
    );

    expect(events).toEqual([
      { event: "text_delta", data: '{"text":"a"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("joins an event split across chunks, wherever the split falls", async () => {
    const text = 'event: text_delta\ndata: {"text":"hello"}\n\nevent: done\ndata: {}\n\n';

    for (let split = 1; split < text.length; split++) {
      const events = await collect(streamOf(text.slice(0, split), text.slice(split)));

      expect(events, `split at ${split}`).toEqual([
        { event: "text_delta", data: '{"text":"hello"}' },
        { event: "done", data: "{}" },
      ]);
    }
  });

  it("reads one byte at a time", async () => {
    const bytes = encoder.encode('event: a\r\ndata: {"text":"é"}\r\n\r\n');
    const events = await collect(streamOf(...Array.from(bytes, (byte) => Uint8Array.of(byte))));

    expect(events).toEqual([{ event: "a", data: '{"text":"é"}' }]);
  });

  it("keeps a character whose bytes are split across chunks", async () => {
    const bytes = encoder.encode("data: é\n\n");
    const events = await collect(streamOf(bytes.slice(0, 7), bytes.slice(7)));

    expect(events).toEqual([{ event: "message", data: "é" }]);
  });

  it("reads CRLF and lone CR line endings", async () => {
    expect(await collect(streamOf("event: a\r\ndata: 1\r\n\r\nevent: b\rdata: 2\r\r"))).toEqual([
      { event: "a", data: "1" },
      { event: "b", data: "2" },
    ]);
  });

  it("does not take a CRLF split across chunks for two line endings", async () => {
    // Read as two line endings, the first would close the event before its data line.
    const events = await collect(streamOf("event: a\r", "\ndata: 1\r", "\n\r", "\n"));

    expect(events).toEqual([{ event: "a", data: "1" }]);
  });

  it("joins the data lines of one event with a newline", async () => {
    expect(await collect(streamOf("data: one\ndata: two\ndata:\ndata: four\n\n"))).toEqual([
      { event: "message", data: "one\ntwo\n\nfour" },
    ]);
  });

  it("removes one leading space of a value only", async () => {
    expect(await collect(streamOf("data:  two spaces\n\ndata:none\n\n"))).toEqual([
      { event: "message", data: " two spaces" },
      { event: "message", data: "none" },
    ]);
  });

  it("skips comments, other fields and events without data", async () => {
    const events = await collect(
      streamOf(": keep-alive\n\nid: 7\nretry: 100\nevent: empty\n\nevent: a\ndata: 1\n\n"),
    );

    expect(events).toEqual([{ event: "a", data: "1" }]);
  });

  it("drops an event the stream ends in the middle of", async () => {
    expect(await collect(streamOf("event: a\ndata: 1\n\nevent: b\ndata: 2\n"))).toEqual([
      { event: "a", data: "1" },
    ]);
  });

  it("reads nothing from an empty stream", async () => {
    expect(await collect(streamOf())).toEqual([]);
  });

  it("cancels the body when the reader stops early", async () => {
    let cancelled = false;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("data: 1\n\ndata: 2\n\n"));
      },
      cancel() {
        cancelled = true;
      },
    });

    for await (const event of readSseEvents(body)) {
      expect(event.data).toBe("1");
      break;
    }

    expect(cancelled).toBe(true);
  });
});
