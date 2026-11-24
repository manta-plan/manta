import { useEffect, useRef, useState } from "react";
import { LuSend, LuSquare } from "react-icons/lu";
import { ApiError } from "../../../api/manta";
import {
  fitHistory,
  streamChatReply,
  useChatStatus,
  type ChatStatus,
  type ChatTurn,
} from "../../chat/api";
import { loadAttributeNames, toChatRecord, type ChatRecord } from "../../chat/record-context";
import { ResultTable } from "../../chat/result-table";
import {
  runSql,
  splitSqlReply,
  sqlErrorMessage,
  type SqlReply,
  type SqlResult,
} from "../../chat/run-sql";
import { useProjectStore } from "../store/project-store";
import type { LoadedRecord } from "../store/types";
import { RaiAnimated, RaiMascot } from "./rai-mascot";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** The query in a finished reply, and how running it went. */
  query?: SqlReply & { result?: SqlResult; error?: string };
  /** Why a reply ended early, or what is happening to it. */
  note?: string;
  /** Why a reply failed. */
  error?: string;
}

const INTRODUCTION =
  "Hi! I'm Rai, the little brother of the famous Manta Ray. Smaller fins, bigger brain (the AI is in my name), and I swim through energy systems instead of oceans.";

const GREETING = `${INTRODUCTION} I can answer questions from the Manta documentation. Questions about your project's results are coming soon.`;

const DATA_GREETING = `${INTRODUCTION} I can answer questions from the Manta documentation. Ask me about this project's data too, and I'll answer with a table. I write the query without seeing the numbers, so check it before you rely on the table.`;

const UNAVAILABLE_GREETING = `${INTRODUCTION} Chat isn't enabled in this deployment. Coming soon: answers from the Manta documentation, and questions about your results, answered with tables.`;

// What the model is to remember: every turn that has text. The greeting isn't
// the model's, and a reply that failed before its first word has none. A
// reply's query is part of its text. Its rows never go to the model.
function toTurns(messages: ChatMessage[], limits: ChatStatus): ChatTurn[] {
  return fitHistory(
    messages
      .filter((message) => message.text !== "")
      .map((message) => ({ role: message.role, content: message.text })),
    limits,
  );
}

const attributeNames = new Map<string, Promise<string[]>>();

// What the scenario on screen contains, for the model to write a query over.
// Read once per record and scenario. Without it (no record loaded, or the
// record server out of reach) the chat still answers from the documentation.
async function describeRecord(record: LoadedRecord | null): Promise<ChatRecord | undefined> {
  if (!record) return undefined;
  const key = `${record.info.id}\n${record.scenario ?? ""}`;
  let names = attributeNames.get(key);
  if (!names) {
    names = loadAttributeNames();
    attributeNames.set(key, names);
  }
  try {
    return toChatRecord(record.entityCounts, record.info.manifest, await names);
  } catch {
    attributeNames.delete(key);
    return undefined;
  }
}

// Typing speed for the greeting, in characters per second.
const TYPE_RATE = 80;

/**
 * Types `text` out once on mount, with a caret. The untyped rest is laid out
 * invisibly so the bubble keeps its final size and nothing reflows. Screen
 * readers get the full text at once; reduced motion skips the effect.
 */
function TypewriterText({ text }: { text: string }) {
  const [count, setCount] = useState(() =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ? text.length : 0,
  );

  const typing = count < text.length;

  useEffect(() => {
    if (!typing) return;
    const start = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const next = Math.min(text.length, Math.floor(((now - start) / 1000) * TYPE_RATE));
      setCount(next);
      if (next < text.length) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
    // Starts once; `typing` only flips when it finishes.
  }, [text, typing]);

  return (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden>
        {text.slice(0, count)}
        {/* Zero-width anchor, so the caret can't push words onto the next line. */}
        {typing && (
          <span className="relative">
            <span className="bg-accent-400 absolute top-0 left-px h-[1.2em] w-[2px] animate-pulse" />
          </span>
        )}
        <span className="invisible">{text.slice(count)}</span>
      </span>
    </>
  );
}

export function AiChatView() {
  const status = useChatStatus();
  const record = useProjectStore((s) => s.record);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isReplying, setIsReplying] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const isEnabled = status?.enabled === true;
  const greeting = !isEnabled
    ? UNAVAILABLE_GREETING
    : status.sql_enabled && record
      ? DATA_GREETING
      : GREETING;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Closing the drawer abandons a reply still being written.
  useEffect(() => () => abortRef.current?.abort(), []);

  const sendMessage = async () => {
    const text = draft.trim();
    if (!text || isReplying || !status?.enabled) return;

    const question: ChatMessage = { id: `u-${Date.now()}`, role: "user", text };
    const replyId = `a-${Date.now()}`;
    const updateReply = (change: (reply: ChatMessage) => ChatMessage) =>
      setMessages((prev) =>
        prev.map((message) => (message.id === replyId ? change(message) : message)),
      );

    setMessages([...messages, question, { id: replyId, role: "assistant", text: "" }]);
    setDraft("");
    setIsReplying(true);
    const controller = new AbortController();
    abortRef.current = controller;

    // Streams one reply into the bubble. Resolves to its text once it is
    // complete, and to null when it failed, which the bubble then says.
    const streamReply = async (turns: ChatTurn[], context?: ChatRecord) => {
      let reply = "";
      for await (const event of streamChatReply(turns, controller.signal, context)) {
        if (event.type === "delta") {
          reply += event.text;
          const soFar = reply;
          updateReply((message) => ({ ...message, text: soFar }));
        } else if (event.type === "error") {
          updateReply((message) => ({ ...message, error: event.message }));
          return null;
        } else if (event.finishReason === "length") {
          updateReply((message) => ({ ...message, note: "Cut off at the length limit." }));
          return null;
        }
      }
      return reply;
    };

    // Runs the query of a complete reply, if it has one, and shows its rows.
    // Resolves to the error of a query that failed.
    const runQuery = async (reply: string) => {
      const query = splitSqlReply(reply);
      if (!query) return undefined;
      updateReply((message) => ({ ...message, query, note: "Running the query…" }));
      try {
        const result = await runSql(query.sql);
        updateReply((message) => ({ ...message, query: { ...query, result }, note: undefined }));
        return undefined;
      } catch (error) {
        const failure = sqlErrorMessage(error);
        updateReply((message) => ({
          ...message,
          query: { ...query, error: failure },
          note: undefined,
        }));
        return failure;
      }
    };

    try {
      const context = status.sql_enabled ? await describeRecord(record) : undefined;
      const turns = toTurns([...messages, question], status);
      const reply = await streamReply(turns, context);
      const failure = reply !== null && context ? await runQuery(reply) : undefined;

      // The model gets one more try, with the error and nothing else: the
      // rows of a query never go to it.
      if (reply !== null && failure !== undefined && !controller.signal.aborted) {
        updateReply((message) => ({
          ...message,
          text: "",
          query: undefined,
          note: "The query failed. Trying once more…",
        }));
        const retryTurns = fitHistory(
          [
            ...turns,
            { role: "assistant", content: reply },
            { role: "user", content: `The query failed: ${failure}\nWrite the corrected query.` },
          ],
          status,
        );
        const retry = await streamReply(retryTurns, context);
        updateReply((message) => ({ ...message, note: undefined }));
        if (retry !== null) await runQuery(retry);
      }
    } catch (error) {
      if (controller.signal.aborted) {
        updateReply((reply) => ({ ...reply, note: "Stopped." }));
      } else {
        // An ApiError carries the backend's own explanation, e.g. that Rai is busy.
        const message =
          error instanceof ApiError ? error.message : "Rai could not be reached. Try again.";
        updateReply((reply) => ({ ...reply, note: undefined, error: message }));
      }
    } finally {
      setIsReplying(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3">
        {/* Shown once the status is known, so the greeting doesn't change mid-sentence. */}
        {status !== undefined && (
          <div className="flex items-start gap-2">
            {/* Rai waves hello on the greeting, then settles. */}
            <RaiAnimated motion="wave" size={24} className="text-accent-500 mt-1.5 shrink-0" />
            <div className="bg-surface-700/60 text-surface-100 max-w-[85%] rounded-lg px-3 py-1.5 text-[12px] leading-relaxed">
              <TypewriterText key={greeting} text={greeting} />
            </div>
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex items-start gap-2 ${message.role === "user" ? "flex-row-reverse" : ""}`}
          >
            {message.role === "assistant" && (
              <RaiMascot size={24} className="text-accent-500 mt-1.5 shrink-0" />
            )}
            {/* The model's text is shown as written, never as HTML or Markdown. */}
            <div
              className={`max-w-[85%] min-w-0 rounded-lg px-3 py-1.5 text-[12px] leading-relaxed break-words whitespace-pre-wrap ${
                message.role === "user"
                  ? "bg-accent-600 text-white"
                  : "bg-surface-700/60 text-surface-100"
              }`}
            >
              {message.query ? <QueryReply query={message.query} /> : message.text}
              {message.role === "assistant" &&
                message.text === "" &&
                message.error === undefined &&
                message.note === undefined && (
                  <span className="text-surface-400 animate-pulse">Rai is thinking…</span>
                )}
              {message.note !== undefined && (
                <span className="text-surface-400 block">{message.note}</span>
              )}
              {message.error !== undefined && (
                <span role="alert" className="text-danger-400 block">
                  {message.error}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="border-surface-600/60 shrink-0 border-t p-2">
        <div className="border-surface-600 bg-surface-900/60 flex items-end gap-1.5 rounded-md border p-1.5">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void sendMessage();
              }
            }}
            placeholder={isEnabled ? "Ask Rai…" : "Chat isn't available"}
            disabled={!isEnabled}
            maxLength={status?.max_message_chars}
            rows={1}
            className="text-surface-100 placeholder:text-surface-500 max-h-24 flex-1 resize-none bg-transparent px-1.5 py-1 text-[12px] outline-none disabled:cursor-not-allowed"
          />
          {isReplying ? (
            <button
              onClick={() => abortRef.current?.abort()}
              aria-label="Stop the reply"
              className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none"
            >
              <LuSquare size={12} />
            </button>
          ) : (
            <button
              onClick={() => void sendMessage()}
              disabled={!isEnabled || !draft.trim()}
              aria-label="Send"
              className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none disabled:pointer-events-none disabled:opacity-40"
            >
              <LuSend size={13} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// A reply that holds a query: its text, the query folded away, and the rows
// the query returned, or why it did not run.
function QueryReply({ query }: { query: NonNullable<ChatMessage["query"]> }) {
  return (
    <div className="space-y-1.5">
      {query.before && <div>{query.before}</div>}
      {query.result && <ResultTable result={query.result} />}
      {query.error !== undefined && (
        <div role="alert" className="text-danger-400">
          The query failed: {query.error}
        </div>
      )}
      {query.after && <div>{query.after}</div>}
      <details className="text-surface-300">
        <summary className="cursor-pointer select-none">Query</summary>
        <pre className="bg-surface-900/60 mt-1 overflow-x-auto rounded p-1.5 font-mono text-[10.5px] whitespace-pre-wrap">
          {query.sql}
        </pre>
      </details>
    </div>
  );
}
