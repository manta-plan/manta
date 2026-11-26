import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  chatReducer,
  initialChatState,
  type ChatAction,
  type ChatState,
} from "../../../chat/conversation";
import type { ChatRun, ChatStatus, ChatStreamEvent } from "../../../chat/types";
import { AiChatPanel, type ChatAvailability } from "../ai-chat-view";

// The panel is rendered to markup, as the tests run without a DOM: what each state shows is
// checked here, what the handlers do in chat/__tests__/conversation.test.ts.
beforeEach(() => {
  vi.stubGlobal("window", { matchMedia: () => ({ matches: true }) });
});

const status: ChatStatus = {
  enabled: true,
  max_messages: 12,
  max_message_chars: 2000,
  max_history_chars: 6000,
  daily_message_limit: 20,
  messages_used_today: 3,
};

function chatAfter(...events: ChatStreamEvent[]): ChatState {
  const actions: ChatAction[] = [
    { type: "send", userId: "u-0", assistantId: "a-0", text: "Why did this run fail?" },
    ...events.map((event): ChatAction => ({ type: "event", event })),
  ];

  return actions.reduce(chatReducer, initialChatState);
}

function render(
  props: {
    availability?: ChatAvailability;
    status?: ChatStatus | null;
    chat?: ChatState;
    draft?: string;
    run?: ChatRun;
  } = {},
) {
  return renderToStaticMarkup(
    <AiChatPanel
      availability={props.availability ?? "ready"}
      status={props.status === null ? undefined : (props.status ?? status)}
      chat={props.chat ?? initialChatState}
      draft={props.draft ?? ""}
      run={props.run ?? null}
      onDraftChange={() => {}}
      onSend={() => {}}
      onStop={() => {}}
      onRetry={() => {}}
      onRemoveRun={() => {}}
      onClear={() => {}}
    />,
  );
}

const sendButton = /<button[^>]*aria-label="Send message"[^>]*>/;
const textarea = /<textarea[^>]*>/;

describe("AiChatPanel", () => {
  it("greets, and shows the disclaimer once and the questions left", () => {
    const html = render({ draft: "Hello" });

    expect(html).toContain("I&#x27;m Rai, the little brother of the famous Manta Ray");
    expect(html).toContain('role="log"');
    expect(html).toContain('aria-live="polite"');
    expect(html.match(/AI answer, check important numbers/g)).toHaveLength(1);
    expect(html.match(/kept only in this browser tab, for up to 2 hours/g)).toHaveLength(1);
    expect(html).toContain("17 of 20 questions left today");
    expect(html).not.toContain("Clear chat");
    expect(html.match(textarea)?.[0]).not.toContain("disabled=");
    expect(html.match(sendButton)?.[0]).not.toContain("disabled=");
  });

  it("does not send an empty message", () => {
    expect(render({ draft: "   " }).match(sendButton)?.[0]).toContain('disabled=""');
  });

  it("turns Send into Stop while a reply is written, and keeps it out of the log until done", () => {
    const html = render({ chat: chatAfter({ type: "text_delta", text: "The solver" }) });

    expect(html).toContain('aria-label="Stop answering"');
    expect(html).not.toMatch(sendButton);
    expect(html.match(/<button[^>]*aria-label="Stop answering"[^>]*>/)?.[0]).not.toContain(
      "disabled=",
    );
    expect(html).toContain("Why did this run fail?");
    expect(html).toContain('aria-hidden="true"><svg');
    expect(html).toContain('<p class="break-words whitespace-pre-wrap">The solver</p>');
    expect(html.match(/AI answer, check important numbers/g)).toHaveLength(1);
    expect(html.match(/kept only in this browser tab, for up to 2 hours/g)).toHaveLength(1);
  });

  it("shows Rai typing before the first word, and a lookup in plain words while it runs", () => {
    expect(render({ chat: chatAfter() })).toContain("Rai is typing…");

    const html = render({
      chat: chatAfter({ type: "tool_call", name: "get_run_logs", label: "Checking run logs" }),
    });

    expect(html).toContain("Checking run logs…");
    expect(html).not.toContain("get_run_logs");
    expect(html).not.toContain("<details");
  });

  it("shows a finished reply with its lookups folded away", () => {
    const html = render({
      chat: chatAfter(
        { type: "tool_call", name: "get_run_logs", label: "Checking run logs" },
        { type: "tool_result_summary", name: "get_run_logs", ok: false },
        { type: "tool_call", name: "search_docs", label: "Searching the docs" },
        { type: "tool_result_summary", name: "search_docs", ok: true },
        { type: "text_delta", text: "Line one\nLine two" },
        { type: "done", finish_reason: "stop" },
      ),
    });

    expect(html).toMatch(sendButton);
    expect(html).not.toContain("Stop answering");
    expect(html).toContain("Line one\nLine two");
    expect(html).toMatch(/<details[^>]*><summary[^>]*>2 lookups<\/summary>/);
    expect(html).not.toMatch(/<details[^>]*open/);
    expect(html).toContain("Checking run logs (failed)");
    expect(html).toContain("<li>Searching the docs</li>");
    expect(html).not.toContain("get_run_logs");
    expect(html).not.toContain("Retry");
  });

  it("offers Clear chat once there is a conversation", () => {
    const html = render({ chat: chatAfter({ type: "done", finish_reason: "stop" }) });

    expect(html.match(/<button[^>]*>Clear chat<\/button>/g)).toHaveLength(1);
    expect(render({ run: { id: "r1", name: "Base case 2030" } })).not.toContain("Clear chat");
  });

  it("does not show the blank lines a reply opens with after a lookup", () => {
    const html = render({
      chat: chatAfter(
        { type: "tool_call", name: "get_run_logs", label: "Checking run logs" },
        { type: "tool_result_summary", name: "get_run_logs", ok: true },
        { type: "text_delta", text: "\n\nThe solver" },
      ),
    });

    expect(html).toContain('<p class="break-words whitespace-pre-wrap">The solver</p>');
  });

  it("renders model text as text, never as markup", () => {
    const html = render({
      chat: chatAfter(
        { type: "text_delta", text: '<img src=x onerror="alert(1)"> **bold**' },
        { type: "done", finish_reason: "stop" },
      ),
    });

    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt; **bold**");
  });

  it("marks a stopped reply and offers no retry", () => {
    const html = render({
      chat: [{ type: "stopped" } as const].reduce(
        chatReducer,
        chatAfter({ type: "text_delta", text: "The sol" }),
      ),
    });

    expect(html).toContain("The sol");
    expect(html).toContain("Stopped.");
    expect(html).toMatch(sendButton);
    expect(html).not.toContain("Retry");
  });

  it("lists numbered sources as text, in order, without a link", () => {
    const html = render({
      chat: chatAfter(
        { type: "text_delta", text: "Start it from the Run tab [1]." },
        {
          type: "citation",
          index: 2,
          title: "Inspect",
          heading_path: "Inspect › Charts",
          url: "user-guide/inspect.md#charts",
        },
        {
          type: "citation",
          index: 1,
          title: "Run",
          heading_path: "Run › Start a run",
          url: "user-guide/run.md#start-a-run",
        },
        { type: "done", finish_reason: "stop" },
      ),
    });

    expect(html).toContain("Sources");
    expect(html).toContain("[1]");
    expect(html).toContain("Run › Start a run");
    expect(html.indexOf("Run › Start a run")).toBeLessThan(html.indexOf("Inspect › Charts"));
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("user-guide/run.md");
  });

  it("shows an error as an alert with a retry", () => {
    const html = render({
      chat: chatAfter(
        { type: "text_delta", text: "The" },
        { type: "error", code: "timeout", message: "upstream read timeout" },
      ),
    });

    expect(html).toMatch(/<p[^>]*role="alert"[^>]*>.*The answer took too long/);
    expect(html).not.toContain("upstream read timeout");
    expect(html).toMatch(/<button[^>]*>Retry<\/button>/);
  });

  it("shows an interrupted reply with what was written and a retry", () => {
    const html = render({
      chat: chatAfter({ type: "text_delta", text: "The solver" }, { type: "interrupted" }),
    });

    expect(html).toContain("The solver");
    expect(html).toMatch(/role="alert"[^>]*>.*The answer was interrupted before it finished/);
    expect(html).toMatch(/<button[^>]*>Retry<\/button>/);
  });

  it("offers a retry on the last reply only", () => {
    const failed = chatAfter({ type: "interrupted" });
    const chat = [
      { type: "send", userId: "u-1", assistantId: "a-1", text: "And now?" } as const,
      { type: "event", event: { type: "done", finish_reason: "stop" } } as const,
    ].reduce(chatReducer, failed);

    expect(render({ chat })).not.toContain("Retry");
  });

  it.each([
    ["chat is turned off", { ...status, enabled: false }],
    ["the status cannot be read", null],
  ])("is disabled and says so when %s", (_case, disabledStatus) => {
    const html = render({ availability: "disabled", status: disabledStatus, draft: "Hello" });

    expect(html).toContain("Chat isn&#x27;t enabled in this deployment. Coming soon");
    expect(html).not.toContain("the little brother");
    expect(html.match(textarea)?.[0]).toContain('disabled=""');
    expect(html.match(sendButton)?.[0]).toContain('disabled=""');
    expect(html.match(sendButton)?.[0]).toContain(
      'title="Chat isn&#x27;t enabled in this deployment"',
    );
    expect(html).not.toContain("questions left today");
  });

  it("waits for the status before greeting, and does not send meanwhile", () => {
    const html = render({ availability: "loading", status: null, draft: "Hello" });

    expect(html).toContain("Rai is typing…");
    expect(html).not.toContain("the little brother");
    expect(html).not.toContain("Chat isn&#x27;t enabled");
    expect(html.match(sendButton)?.[0]).toContain('disabled=""');
  });

  it("says in words when the daily questions are used up, and stops taking input", () => {
    const html = render({
      status: { ...status, messages_used_today: 20 },
      draft: "One more",
      chat: chatAfter({ type: "interrupted" }),
    });

    expect(html).toMatch(
      /role="status".*You have used all of today&#x27;s questions \(20 of 20\)\. Try again tomorrow\./,
    );
    expect(html).toContain("0 of 20 questions left today");
    expect(html.match(textarea)?.[0]).toContain('disabled=""');
    expect(html.match(sendButton)?.[0]).toContain('disabled=""');
    expect(html).not.toContain("Retry");
  });

  it("shows no meter when the deployment sets no daily limit", () => {
    const html = render({ status: { ...status, daily_message_limit: 0 }, draft: "Hello" });

    expect(html).not.toContain("questions left today");
    expect(html.match(sendButton)?.[0]).not.toContain("disabled=");
  });

  it("counts characters near the limit and refuses a message over it", () => {
    const short = { ...status, max_message_chars: 10 };

    expect(render({ status: short, draft: "1234567" })).not.toContain("characters");
    expect(render({ status: short, draft: "12345678" })).toContain("8 of 10 characters");

    const over = render({ status: short, draft: "123456789012" });

    expect(over).toContain("Too long by 2 characters (the limit is 10).");
    expect(over.match(sendButton)?.[0]).toContain('disabled=""');
    expect(over.match(textarea)?.[0]).toContain('aria-invalid="true"');
  });

  it("holds a message to the history limit when that is the smaller one", () => {
    const html = render({
      status: { ...status, max_message_chars: 2000, max_history_chars: 10 },
      draft: "123456789012",
    });

    expect(html).toContain("Too long by 2 characters (the limit is 10).");
    expect(html.match(sendButton)?.[0]).toContain('disabled=""');
  });

  it("shows the run it is about, removable until the conversation starts", () => {
    const run = { id: "r1", name: "Base case 2030" };
    const before = render({ run });
    const after = render({ run, chat: chatAfter({ type: "done", finish_reason: "stop" }) });

    expect(before).toContain("Run: Base case 2030");
    expect(before).toContain('aria-label="Context: run Base case 2030, remove"');
    expect(after).toContain("Run: Base case 2030");
    expect(after).not.toContain("Context: run Base case 2030, remove");
    expect(render()).not.toContain("Run:");
  });
});
