import { useEffect, useEffectEvent, useReducer, useRef, useState } from "react";
import { LuCircleAlert, LuSend, LuSquare, LuWorkflow, LuX } from "react-icons/lu";
import { useSessionUser } from "../../auth/session";
import { useChatStatus } from "../../chat/api";
import {
  buildHistory,
  canRetry,
  chatReducer,
  questionsLeft,
  runChatTurn,
  type ChatMessage,
  type ChatState,
} from "../../chat/conversation";
import { chatRetentionMs, loadStoredChat, saveStoredChat } from "../../chat/storage";
import type { ChatHistoryMessage, ChatRun, ChatStatus } from "../../chat/types";
import { RaiAnimated, RaiMascot } from "./rai-mascot";

const GREETING =
  "Hi! I'm Rai, the little brother of the famous Manta Ray. Smaller fins, bigger brain (the AI is in my name), and I swim through energy systems instead of oceans. Ask me about your project, scenarios, or results!";

// Shown when the deployment has chat turned off, and when its status cannot be read.
const DISABLED_GREETING =
  "Chat isn't enabled in this deployment. Coming soon: answers from the Manta documentation, and questions about your results, answered with tables.";

// The share of the message limit from which the character count shows.
const COUNTER_FROM = 0.8;

const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Typing speed for the greeting, in characters per second.
const TYPE_RATE = 80;

/**
 * Types `text` out once on mount, with a caret. The untyped rest is laid out
 * invisibly so the bubble keeps its final size and nothing reflows. Screen
 * readers get the full text at once; reduced motion skips the effect.
 */
function TypewriterText({ text }: { text: string }) {
  const [count, setCount] = useState(() => (prefersReducedMotion() ? text.length : 0));

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

/** `loading` until the chat status is known; `disabled` when chat is off or the status failed. */
export type ChatAvailability = "loading" | "disabled" | "ready";

const typingClassName = "text-surface-400 animate-pulse motion-reduce:animate-none";

// One reply of Rai: the text as plain text, then what it looked up, its sources and how it ended.
function AssistantMessage({ message, onRetry }: { message: ChatMessage; onRetry?: () => void }) {
  const isStreaming = message.status === "streaming";
  const runningTool = message.tools.findLast((tool) => tool.state === "running");
  const hasFailed = canRetry(message);
  // A reply may open with blank lines, after a lookup.
  const text = message.text.trim();

  return (
    // Hidden from screen readers while it is written, so the log announces it once, finished.
    <div className="flex items-start gap-2" aria-hidden={isStreaming || undefined}>
      <RaiMascot size={24} className="text-accent-500 mt-1.5 shrink-0" />
      <div className="bg-surface-700/60 text-surface-100 max-w-[85%] rounded-lg px-3 py-1.5 text-[12px] leading-relaxed">
        {text !== "" && <p className="break-words whitespace-pre-wrap">{text}</p>}
        {isStreaming && (text === "" || runningTool !== undefined) && (
          <p className={typingClassName}>
            {runningTool === undefined ? "Rai is typing…" : `${runningTool.label}…`}
          </p>
        )}
        {!isStreaming && message.tools.length > 0 && (
          <details className="text-surface-300 mt-1 text-[11px]">
            <summary className="hover:text-surface-100 focus-visible:text-surface-50 cursor-pointer outline-none focus-visible:underline">
              {message.tools.length === 1 ? "1 lookup" : `${message.tools.length} lookups`}
            </summary>
            <ul className="mt-0.5 space-y-0.5 pl-3">
              {message.tools.map((tool, index) => (
                // Only ever appended to, so the position is a stable key.
                <li key={index}>
                  {tool.label}
                  {tool.state === "failed" && " (failed)"}
                </li>
              ))}
            </ul>
          </details>
        )}
        {message.citations.length > 0 && (
          <div className="border-surface-600/60 mt-1.5 border-t pt-1.5 text-[11px]">
            <p className="text-surface-300 font-semibold tracking-wide uppercase">Sources</p>
            <ol className="mt-0.5 space-y-0.5">
              {message.citations.map((citation) => (
                <li key={citation.index} className="flex gap-1.5">
                  <span className="text-surface-300 shrink-0">[{citation.index}]</span>
                  <span className="break-words">
                    {citation.title}
                    {citation.heading_path !== "" && citation.heading_path !== citation.title && (
                      <span className="text-surface-300"> · {citation.heading_path}</span>
                    )}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {message.note !== null &&
          (hasFailed ? (
            <p className="mt-1 flex items-start gap-1.5" role="alert">
              <LuCircleAlert size={12} className="text-danger-500 mt-1 shrink-0" aria-hidden />
              {message.note}
            </p>
          ) : (
            <p className="text-surface-300 mt-1 text-[11px]">{message.note}</p>
          ))}
        {hasFailed && onRetry !== undefined && (
          <button
            type="button"
            onClick={onRetry}
            className="border-surface-600 text-surface-200 hover:bg-surface-700 focus-visible:bg-surface-700 mt-1.5 rounded border px-2 py-0.5 text-[11px] font-medium outline-none"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

interface AiChatPanelProps {
  availability: ChatAvailability;
  /** Undefined until it has loaded, and when it could not be read. */
  status: ChatStatus | undefined;
  chat: ChatState;
  draft: string;
  /** The run the conversation is about; fixed once the conversation has started. */
  run: ChatRun | null;
  onDraftChange: (draft: string) => void;
  /** Called with the trimmed text, only when it can be sent. */
  onSend: (text: string) => void;
  onStop: () => void;
  onRetry: () => void;
  onRemoveRun: () => void;
  /** Empties the conversation, on screen and in the tab's storage. */
  onClear: () => void;
}

/** The chat as it looks for a given state; `AiChatView` gives it the state and does the work. */
export function AiChatPanel({
  availability,
  status,
  chat,
  draft,
  run,
  onDraftChange,
  onSend,
  onStop,
  onRetry,
  onRemoveRun,
  onClear,
}: AiChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { messages, isStreaming } = chat;

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      // Smooth scrolling can't keep up with a reply that grows many times a second.
      behavior: isStreaming || prefersReducedMotion() ? "auto" : "smooth",
    });
  }, [messages, isStreaming, availability]);

  const text = draft.trim();
  const left = status === undefined ? null : questionsLeft(status);
  const isOutOfQuestions = availability === "ready" && left === 0;
  // One request carries the whole history, so a message can be no longer than that either.
  const charLimit =
    status === undefined ? 0 : Math.min(status.max_message_chars, status.max_history_chars);
  const maxChars = charLimit > 0 ? charLimit : null;
  const isTooLong = maxChars !== null && text.length > maxChars;
  const showsCounter = maxChars !== null && text.length >= maxChars * COUNTER_FROM;
  const canSend = availability === "ready" && !isOutOfQuestions && text !== "" && !isTooLong;
  const hasStarted = messages.length > 0;
  const sendTitle =
    availability === "disabled"
      ? "Chat isn't enabled in this deployment"
      : isOutOfQuestions
        ? "No questions left today"
        : isTooLong
          ? "The message is too long"
          : "Send message";

  const send = () => {
    if (canSend && !isStreaming) onSend(text);
  };

  return (
    <div className="flex h-full flex-col">
      <div
        ref={scrollRef}
        role="log"
        aria-live="polite"
        aria-label="Conversation with Rai"
        className="flex-1 space-y-3 overflow-y-auto p-3"
      >
        {availability === "loading" ? (
          <div className="flex items-start gap-2">
            <RaiMascot size={24} className="text-accent-500 mt-1.5 shrink-0" />
            <div className="bg-surface-700/60 rounded-lg px-3 py-1.5 text-[12px]">
              <span className={typingClassName}>Rai is typing…</span>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-2">
            {/* Rai waves hello on the greeting, then settles. */}
            <RaiAnimated motion="wave" size={24} className="text-accent-500 mt-1.5 shrink-0" />
            <div className="bg-surface-700/60 text-surface-100 max-w-[85%] rounded-lg px-3 py-1.5 text-[12px] leading-relaxed">
              <TypewriterText
                key={availability}
                text={availability === "ready" ? GREETING : DISABLED_GREETING}
              />
            </div>
          </div>
        )}
        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={message.id} className="flex flex-row-reverse items-start gap-2">
              <div className="bg-accent-600 max-w-[85%] rounded-lg px-3 py-1.5 text-[12px] leading-relaxed break-words whitespace-pre-wrap text-white">
                {message.text}
              </div>
            </div>
          ) : (
            <AssistantMessage
              // A finished reply is a new element, which is what makes the log announce it.
              key={message.status === "streaming" ? `${message.id}:streaming` : message.id}
              message={message}
              onRetry={
                index === messages.length - 1 && availability === "ready" && !isOutOfQuestions
                  ? onRetry
                  : undefined
              }
            />
          ),
        )}
      </div>

      <div className="border-surface-600/60 shrink-0 border-t p-2">
        {run !== null && (
          <div className="mb-1.5 flex">
            <span className="border-surface-600 bg-surface-700/60 text-surface-200 inline-flex max-w-full items-center gap-1 rounded border py-0.5 pr-1 pl-1.5 text-[11px]">
              <LuWorkflow size={11} className="shrink-0" aria-hidden />
              <span className="truncate" title={run.name}>
                Run: {run.name}
              </span>
              {!hasStarted && (
                <button
                  type="button"
                  aria-label={`Context: run ${run.name}, remove`}
                  title="Ask without this run"
                  onClick={onRemoveRun}
                  className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 focus-visible:bg-surface-700 focus-visible:text-surface-50 shrink-0 rounded p-0.5 outline-none"
                >
                  <LuX size={11} />
                </button>
              )}
            </span>
          </div>
        )}
        {isOutOfQuestions && status !== undefined && (
          <p
            className="text-surface-100 mb-1.5 flex items-start gap-1.5 px-1 text-[11px]"
            role="status"
          >
            <LuCircleAlert size={12} className="text-warn-500 mt-0.5 shrink-0" aria-hidden />
            <span>
              You have used all of today&apos;s questions ({status.messages_used_today} of{" "}
              {status.daily_message_limit}). Try again tomorrow.
            </span>
          </p>
        )}
        <div className="border-surface-600 bg-surface-900/60 flex items-end gap-1.5 rounded-md border p-1.5">
          <textarea
            aria-label="Message to Rai"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask Rai…"
            rows={1}
            disabled={availability === "disabled" || isOutOfQuestions}
            aria-invalid={isTooLong || undefined}
            className="text-surface-100 placeholder:text-surface-500 max-h-24 flex-1 resize-none bg-transparent px-1.5 py-1 text-[12px] outline-none disabled:cursor-not-allowed"
          />
          {/* One button for both, so the keyboard focus stays put when Send turns into Stop. */}
          <button
            type="button"
            onClick={isStreaming ? onStop : send}
            disabled={!isStreaming && !canSend}
            aria-label={isStreaming ? "Stop answering" : "Send message"}
            title={isStreaming ? "Stop answering" : sendTitle}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 focus-visible:bg-surface-700 focus-visible:text-surface-50 flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none disabled:pointer-events-none disabled:opacity-40"
          >
            {isStreaming ? <LuSquare size={12} /> : <LuSend size={13} />}
          </button>
        </div>
        {showsCounter && (
          <p className="text-surface-200 mt-1 px-1 text-right text-[10px]" aria-live="polite">
            {isTooLong
              ? `Too long by ${text.length - maxChars} characters (the limit is ${maxChars}).`
              : `${text.length} of ${maxChars} characters`}
          </p>
        )}
        <div className="text-surface-300 mt-1.5 px-1 text-[10px]">
          <p>
            AI answer, check important numbers. This chat is kept only in this browser tab, for up
            to 2 hours.
          </p>
          <div className="mt-0.5 flex items-center justify-between gap-x-3">
            <span>
              {availability === "ready" &&
                status !== undefined &&
                left !== null &&
                `${left} of ${status.daily_message_limit} questions left today`}
            </span>
            {hasStarted && (
              <button
                type="button"
                onClick={onClear}
                className="text-surface-200 hover:bg-surface-700 hover:text-surface-50 focus-visible:bg-surface-700 focus-visible:text-surface-50 -mr-1 shrink-0 rounded px-1 outline-none"
              >
                Clear chat
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * The Rai chat of the right drawer. The server keeps no conversation: each question goes out
 * with the history that fits, and the visible conversation is kept in this tab's sessionStorage
 * for two hours, so it is still there after a reload or when the drawer is opened again. `run`
 * and `question` are what a run's "Why did this fail?" opens it with: a new conversation, in
 * place of the one kept.
 */
export function AiChatView({ run, question }: { run?: ChatRun; question?: string }) {
  const { status, hasFailed, refresh } = useChatStatus();
  // The conversation is kept per user, so that another user of this tab never reads it.
  const userId = useSessionUser()?.claims.sub ?? null;
  const [kept] = useState(() =>
    run !== undefined || question !== undefined || userId === null ? null : loadStoredChat(userId),
  );
  const [chat, dispatch] = useReducer(chatReducer, {
    messages: kept?.messages ?? [],
    isStreaming: false,
  });
  const [draft, setDraft] = useState(question ?? "");
  const [runContext, setRunContext] = useState<ChatRun | null>(run ?? kept?.run ?? null);
  // When the conversation was last stored; null while nothing is.
  const [savedAt, setSavedAt] = useState<number | null>(kept?.savedAt ?? null);
  // What the storage holds, to write only on a change. Null messages: not known to match.
  const stored = useRef<{
    messages: ChatMessage[] | null;
    run: ChatRun | null;
    openReplyId: string | null;
  }>({ messages: kept?.messages ?? null, run: kept?.run ?? null, openReplyId: null });
  const abortController = useRef<AbortController | null>(null);
  const nextMessageNumber = useRef(0);

  // Leaving the view stops the reply being written.
  useEffect(() => () => abortController.current?.abort(), []);

  // Keeps the conversation as it changes. A reply is stored once when it opens and once when it
  // ends, not for every word in between.
  useEffect(() => {
    if (userId === null) {
      return;
    }

    const openReplyId = chat.isStreaming ? (chat.messages.at(-1)?.id ?? null) : null;
    const last = stored.current;

    if (
      last.run === runContext &&
      (last.messages === chat.messages ||
        (openReplyId !== null && last.openReplyId === openReplyId))
    ) {
      return;
    }

    stored.current = { messages: chat.messages, run: runContext, openReplyId };
    setSavedAt(saveStoredChat(userId, { messages: chat.messages, run: runContext }));
  }, [chat, runContext, userId]);

  const clearChat = () => {
    abortController.current?.abort();
    // Whatever the stopped reply still reports belongs to no conversation.
    abortController.current = null;
    dispatch({ type: "clear" });
    setRunContext(null);
  };

  // An open view drops the conversation at the moment it expires; emptying it empties the storage.
  const expire = useEffectEvent(clearChat);
  useEffect(() => {
    if (savedAt === null) {
      return;
    }

    const timer = setTimeout(expire, Math.max(0, savedAt + chatRetentionMs - Date.now()));

    return () => clearTimeout(timer);
  }, [savedAt]);

  const availability: ChatAvailability =
    status === undefined
      ? hasFailed
        ? "disabled"
        : "loading"
      : status.enabled
        ? "ready"
        : "disabled";

  // The reducer has opened a reply before this is called; a turn ends before the next can start.
  const ask = (messages: ChatHistoryMessage[]) => {
    const controller = new AbortController();
    abortController.current = controller;

    void runChatTurn(
      { messages, runUuid: runContext?.id ?? null, signal: controller.signal },
      (action) => {
        if (abortController.current === controller) dispatch(action);
      },
      refresh,
    );
  };

  // Unique among the messages read back from storage too.
  const nextId = (prefix: string) => `${prefix}-${Date.now()}-${nextMessageNumber.current++}`;

  const handleSend = (text: string) => {
    if (status === undefined) {
      return;
    }

    dispatch({ type: "send", userId: nextId("u"), assistantId: nextId("a"), text });
    setDraft("");
    ask(buildHistory(chat.messages, text, status));
  };

  const handleRetry = () => {
    const asked = chat.messages.findLastIndex((message) => message.role === "user");

    if (asked === -1 || chat.isStreaming || status === undefined) {
      return;
    }

    dispatch({ type: "retry", assistantId: nextId("a") });
    ask(buildHistory(chat.messages.slice(0, asked), chat.messages[asked].text, status));
  };

  return (
    <AiChatPanel
      availability={availability}
      status={status}
      chat={chat}
      draft={draft}
      run={runContext}
      onDraftChange={setDraft}
      onSend={handleSend}
      onStop={() => abortController.current?.abort()}
      onRetry={handleRetry}
      onRemoveRun={() => setRunContext(null)}
      onClear={clearChat}
    />
  );
}
