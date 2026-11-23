import { describe, expect, it } from "vitest";
import { readSseEvents, type SseEvent } from "../sse";

function streamOf(...chunks: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function eventsOf(...chunks: string[]) {
  const events: SseEvent[] = [];
  for await (const event of readSseEvents(streamOf(...chunks))) events.push(event);
  return events;
}

describe("readSseEvents", () => {
  it("reads named events with their data", async () => {
    const events = await eventsOf(
      'event: delta\ndata: {"text": "Hi"}\n\nevent: done\ndata: {"finish_reason": "stop"}\n\n',
    );

    expect(events).toEqual([
      { event: "delta", data: '{"text": "Hi"}' },
      { event: "done", data: '{"finish_reason": "stop"}' },
    ]);
  });

  it("joins an event split across chunks, also inside a line", async () => {
    const events = await eventsOf("event: del", 'ta\ndata: {"te', 'xt": "Hi"}\n', "\n");

    expect(events).toEqual([{ event: "delta", data: '{"text": "Hi"}' }]);
  });

  it("skips comment lines, such as keep-alive pings", async () => {
    const events = await eventsOf(": ping\n\nevent: delta\ndata: 1\n\n: ping\n\n");

    expect(events).toEqual([{ event: "delta", data: "1" }]);
  });

  it("accepts CRLF line endings, also when a chunk ends between the CR and the LF", async () => {
    const events = await eventsOf(
      "event: delta\r\ndata: 1\r",
      "\n\r",
      "\nevent: done\r\ndata: 2\r\n\r\n",
    );

    expect(events).toEqual([
      { event: "delta", data: "1" },
      { event: "done", data: "2" },
    ]);
  });

  it("names an event without an event field 'message', and joins its data lines", async () => {
    const events = await eventsOf("data: one\ndata: two\n\n");

    expect(events).toEqual([{ event: "message", data: "one\ntwo" }]);
  });

  it("drops an event the stream ends in the middle of", async () => {
    const events = await eventsOf("event: delta\ndata: 1\n\nevent: delta\ndata: 2\n");

    expect(events).toEqual([{ event: "delta", data: "1" }]);
  });
});
