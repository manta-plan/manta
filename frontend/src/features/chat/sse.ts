export interface SseEvent {
  /** The event's name; "message" when the stream gives none. */
  event: string;
  data: string;
}

/**
 * The events of a `text/event-stream` body, as they arrive. `EventSource`
 * can't be used for the chat: it only sends GET requests, without the
 * Authorization header. Comment lines (the server's keep-alive pings) are
 * skipped, and an event the stream ends in the middle of is dropped.
 */
export async function* readSseEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  // Streaming mode: a character split across two chunks is held back, not garbled.
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "";
  let data: string[] = [];
  // A chunk may end between the CR and the LF of one line ending.
  let skipLineFeed = false;

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;

      const decoded = decoder.decode(value, { stream: true });
      const text: string = skipLineFeed && decoded.startsWith("\n") ? decoded.slice(1) : decoded;
      skipLineFeed = text.endsWith("\r");
      const lines = (buffer + text).split(/\r\n|\n|\r/);
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line === "") {
          if (data.length > 0) yield { event: event || "message", data: data.join("\n") };
          event = "";
          data = [];
          continue;
        }
        if (line.startsWith(":")) continue;

        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const fieldValue = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "event") event = fieldValue;
        else if (field === "data") data.push(fieldValue);
      }
    }
  } finally {
    // Also reached when the consumer stops early: closes the connection.
    await reader.cancel().catch(() => {});
  }
}
