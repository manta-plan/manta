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
import { RaiAnimated, RaiMascot } from "./rai-mascot";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** Why a reply ended early: stopped by the user, or cut off at the length limit. */
  note?: string;
  /** Why a reply failed. */
  error?: string;
}

const INTRODUCTION =
  "Hi! I'm Rai, the little brother of the famous Manta Ray. Smaller fins, bigger brain (the AI is in my name), and I swim through energy systems instead of oceans.";

const GREETING = `${INTRODUCTION} I can answer questions from the Manta documentation. Questions about your project's results are coming soon.`;

const UNAVAILABLE_GREETING = `${INTRODUCTION} Chat isn't enabled in this deployment. Coming soon: answers from the Manta documentation, and questions about your results, answered with tables.`;

// What the model is to remember: every turn that has text. The greeting isn't
// the model's, and a reply that failed before its first word has none.
function toTurns(messages: ChatMessage[], limits: ChatStatus): ChatTurn[] {
  return fitHistory(
    messages
      .filter((message) => message.text !== "")
      .map((message) => ({ role: message.role, content: message.text })),
    limits,
  );
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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isReplying, setIsReplying] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const isEnabled = status?.enabled === true;

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

    try {
      const turns = toTurns([...messages, question], status);
      for await (const event of streamChatReply(turns, controller.signal)) {
        if (event.type === "delta") {
          updateReply((reply) => ({ ...reply, text: reply.text + event.text }));
        } else if (event.type === "error") {
          updateReply((reply) => ({ ...reply, error: event.message }));
        } else if (event.finishReason === "length") {
          updateReply((reply) => ({ ...reply, note: "Cut off at the length limit." }));
        }
      }
    } catch (error) {
      if (controller.signal.aborted) {
        updateReply((reply) => ({ ...reply, note: "Stopped." }));
      } else {
        // An ApiError carries the backend's own explanation, e.g. that Rai is busy.
        const message =
          error instanceof ApiError ? error.message : "Rai could not be reached. Try again.";
        updateReply((reply) => ({ ...reply, error: message }));
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
              <TypewriterText text={isEnabled ? GREETING : UNAVAILABLE_GREETING} />
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
              className={`max-w-[85%] rounded-lg px-3 py-1.5 text-[12px] leading-relaxed break-words whitespace-pre-wrap ${
                message.role === "user"
                  ? "bg-accent-600 text-white"
                  : "bg-surface-700/60 text-surface-100"
              }`}
            >
              {message.text}
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
