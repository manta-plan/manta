/** One server-sent event: its name (`message` when the server gives none) and its data. */
export type SseEvent = {
  event: string;
  data: string;
};

/**
 * Reads a `text/event-stream` body as events. A chunk may end anywhere: in the middle of a line,
 * of a character, or between the CR and the LF of a line ending. Lines end in LF, CRLF or CR, and
 * an event's `data` lines are joined with a newline. An event that is not closed by a blank line
 * when the stream ends is dropped, as the format says. Leaving the loop early cancels the body.
 */
export async function* readSseEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "";
  let data: string[] = [];

  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });

      const lineEnd = /\r\n|\n|\r/g;
      let lineStart = 0;

      for (let match = lineEnd.exec(buffer); match !== null; match = lineEnd.exec(buffer)) {
        // A CR at the very end may be the first half of a CRLF the next chunk completes.
        if (match[0] === "\r" && match.index === buffer.length - 1 && !done) {
          break;
        }

        const line = buffer.slice(lineStart, match.index);
        lineStart = match.index + match[0].length;

        if (line === "") {
          // A blank line closes the event. One without data is not an event.
          if (data.length > 0) {
            yield { event: event || "message", data: data.join("\n") };
          }

          event = "";
          data = [];
          continue;
        }

        // A comment, which servers send to keep the connection open.
        if (line.startsWith(":")) {
          continue;
        }

        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const rest = colon === -1 ? "" : line.slice(colon + 1);
        const fieldValue = rest.startsWith(" ") ? rest.slice(1) : rest;

        if (field === "event") {
          event = fieldValue;
        } else if (field === "data") {
          data.push(fieldValue);
        }
      }

      buffer = buffer.slice(lineStart);

      if (done) {
        return;
      }
    }
  } finally {
    // Closes the connection when the reader stops early; a no-op once the stream has ended.
    await reader.cancel().catch(() => {});
  }
}
