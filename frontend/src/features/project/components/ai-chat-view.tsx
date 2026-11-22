import { useEffect, useRef, useState } from "react";
import { LuSend } from "react-icons/lu";
import { RaiAnimated, RaiMascot } from "./rai-mascot";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: "welcome",
    role: "assistant",
    text: "Hi! I'm Rai, the little brother of the famous Manta Ray. Smaller fins, bigger brain (the AI is in my name), and I swim through energy systems instead of oceans. Ask me about your project, scenarios, or results!",
  },
];

const CANNED_REPLIES = [
  "Based on the current scenario, solar and wind together make up about 42% of installed capacity.",
  "I can help with that once you run the scenario — try clicking Run in the toolbar.",
  "The demand_timeseries data covers Jan–Dec 2026 at hourly resolution.",
  "Quick summary: 12 generators, 3 storage units, and 48 buses are defined in this model.",
  "That metric isn't available yet, but I can pull it from Results once a scenario has been run.",
];

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
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [draft, setDraft] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isTyping]);

  const sendMessage = () => {
    const text = draft.trim();
    if (!text) return;

    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", text }]);
    setDraft("");
    setIsTyping(true);

    const reply = CANNED_REPLIES[Math.floor(Math.random() * CANNED_REPLIES.length)];
    setTimeout(() => {
      setIsTyping(false);
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", text: reply }]);
    }, 700);
  };

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex items-start gap-2 ${message.role === "user" ? "flex-row-reverse" : ""}`}
          >
            {message.role === "assistant" &&
              // Rai waves hello on the greeting, then settles.
              (message.id === "welcome" ? (
                <RaiAnimated motion="wave" size={24} className="text-accent-500 mt-1.5 shrink-0" />
              ) : (
                <RaiMascot size={24} className="text-accent-500 mt-1.5 shrink-0" />
              ))}
            <div
              className={`max-w-[85%] rounded-lg px-3 py-1.5 text-[12px] leading-relaxed ${
                message.role === "user"
                  ? "bg-accent-600 text-white"
                  : "bg-surface-700/60 text-surface-100"
              }`}
            >
              {message.id === "welcome" ? <TypewriterText text={message.text} /> : message.text}
            </div>
          </div>
        ))}
        {isTyping && (
          <div className="flex items-start gap-2">
            <RaiMascot size={24} className="text-accent-500 mt-1.5 shrink-0" />
            <div className="bg-surface-700/60 text-surface-400 rounded-lg px-3 py-1.5 text-[12px]">
              <span className="animate-pulse">Rai is typing…</span>
            </div>
          </div>
        )}
      </div>

      <div className="border-surface-600/60 shrink-0 border-t p-2">
        <div className="border-surface-600 bg-surface-900/60 flex items-end gap-1.5 rounded-md border p-1.5">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Ask Rai…"
            rows={1}
            className="text-surface-100 placeholder:text-surface-500 max-h-24 flex-1 resize-none bg-transparent px-1.5 py-1 text-[12px] outline-none"
          />
          <button
            onClick={sendMessage}
            disabled={!draft.trim()}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none disabled:pointer-events-none disabled:opacity-40"
          >
            <LuSend size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
