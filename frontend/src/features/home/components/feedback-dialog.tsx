import { useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useLocation } from "wouter";
import clsx from "clsx";
import type { IconType } from "react-icons";
import {
  LuBug,
  LuCircleCheck,
  LuImagePlus,
  LuLightbulb,
  LuLoaderCircle,
  LuMessageSquareText,
  LuX,
} from "react-icons/lu";
import { sendFeedback, type FeedbackKind } from "../lib/send-feedback";
import {
  FEEDBACK_IMAGE_TYPES,
  FeedbackImageError,
  formatImageSize,
  prepareFeedbackImage,
} from "../lib/feedback-image";
import { useAppStore } from "../store";
import { useFeedbackDraft } from "../lib/feedback-draft";

const KINDS: { value: FeedbackKind; label: string; icon: IconType; placeholder: string }[] = [
  {
    value: "bug",
    label: "Bug",
    icon: LuBug,
    placeholder: "What happened, and what did you expect instead?",
  },
  {
    value: "idea",
    label: "Idea",
    icon: LuLightbulb,
    placeholder: "What would you like Manta to do?",
  },
  { value: "other", label: "Other", icon: LuMessageSquareText, placeholder: "Tell us anything." },
];

// Rows land in the team's feedback Google Sheet via sendFeedback.
export function FeedbackDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [location] = useLocation();
  const theme = useAppStore((s) => s.theme);
  const { kind, message, includePage, image, update, setImage, clear } = useFeedbackDraft();
  const [website, setWebsite] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSent, setIsSent] = useState(false);
  const [isPreparingImage, setIsPreparingImage] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const [isDraggingImage, setIsDraggingImage] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeKind = KINDS.find((k) => k.value === kind) ?? KINDS[0];
  const canSend = message.trim().length > 0 && !isSending && !isPreparingImage;

  const attachImage = async (file: File) => {
    setImageError(null);
    setIsPreparingImage(true);
    try {
      setImage(await prepareFeedbackImage(file));
    } catch (err) {
      setImageError(
        err instanceof FeedbackImageError ? err.message : "Couldn't attach that image.",
      );
    } finally {
      setIsPreparingImage(false);
    }
  };

  // Pasting a screenshot (e.g. after Cmd+Shift+Ctrl+4) into the message
  // attaches it; ordinary text pastes are left alone.
  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const file = Array.from(event.clipboardData.files).find((item) =>
      item.type.startsWith("image/"),
    );
    if (!file) return;
    event.preventDefault();
    void attachImage(file);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDraggingImage(false);
    const file = event.dataTransfer.files[0];
    if (file) void attachImage(file);
  };

  const submit = async () => {
    if (!canSend) return;
    setIsSending(true);
    setError(null);
    try {
      await sendFeedback({
        type: kind,
        message: message.trim(),
        page: includePage ? location : "",
        theme,
        website,
        image: image ? { name: image.name, type: image.type, base64: image.base64 } : undefined,
      });
      setIsSent(true);
    } catch (err) {
      // The sheet rejects bad images with a specific reason; anything else is
      // most likely the network.
      const reason = err instanceof Error ? err.message : "";
      setError(
        /^(Image too large|Invalid image type)$/.test(reason)
          ? `The screenshot couldn't be uploaded (${reason.toLowerCase()}). Remove it or try another.`
          : "Couldn't send your feedback. Check your connection and try again.",
      );
    } finally {
      setIsSending(false);
    }
  };

  const handleOpenChange = (next: boolean) => {
    onOpenChange(next);
    if (!next) {
      // The draft stays so the dialog can be reopened to carry on; only a
      // sent message is cleared.
      if (isSent) clear();
      setWebsite("");
      setError(null);
      setIsSent(false);
      setImageError(null);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 w-[440px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl shadow-black/50 outline-none">
          <div className="mb-1 flex items-center justify-between">
            <Dialog.Title className="text-surface-50 text-[14px] font-semibold">
              Send Feedback
            </Dialog.Title>
            <Dialog.Close
              className="text-surface-400 hover:text-surface-100 outline-none"
              aria-label="Close"
            >
              <LuX size={16} />
            </Dialog.Close>
          </div>

          {isSent ? (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <LuCircleCheck size={28} className="text-ok-500" />
              <div className="text-surface-50 text-[13px] font-medium">
                Thanks for the feedback!
              </div>
              <Dialog.Description className="text-surface-400 text-[12px]">
                It helps us decide what to fix and build next.
              </Dialog.Description>
              <Dialog.Close className="bg-accent-600 hover:bg-accent-500 mt-3 h-8 rounded px-3 text-[12px] font-medium text-white outline-none">
                Done
              </Dialog.Close>
            </div>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <Dialog.Description className="text-surface-400 mb-4 text-[12px]">
                Found a bug or have an idea? Let us know what's working and what isn't.
              </Dialog.Description>

              <div role="radiogroup" aria-label="Feedback type" className="grid grid-cols-3 gap-2">
                {KINDS.map((option) => {
                  const Icon = option.icon;
                  const selected = option.value === kind;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => update({ kind: option.value })}
                      className={clsx(
                        "flex h-9 items-center justify-center gap-1.5 rounded border text-[12px] font-medium outline-none transition-colors",
                        selected
                          ? "border-accent-500 bg-accent-600/15 text-surface-50"
                          : "border-surface-600 bg-surface-900 text-surface-300 hover:border-surface-500 hover:text-surface-100",
                      )}
                    >
                      <Icon size={14} className={selected ? "text-accent-400" : undefined} />
                      {option.label}
                    </button>
                  );
                })}
              </div>

              <label className="mt-4 flex flex-col gap-1">
                <span className="text-surface-400 text-[11px] font-medium">Message</span>
                <textarea
                  value={message}
                  onChange={(event) => update({ message: event.target.value })}
                  placeholder={activeKind.placeholder}
                  onPaste={handlePaste}
                  rows={5}
                  autoFocus
                  className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 resize-none rounded border px-2 py-1.5 text-[13px] outline-none"
                />
              </label>

              <div className="mt-3 flex flex-col gap-1">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={FEEDBACK_IMAGE_TYPES.join(",")}
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    // Reset so picking the same file again still fires onChange.
                    event.target.value = "";
                    if (file) void attachImage(file);
                  }}
                />
                {image ? (
                  <div className="border-surface-600 bg-surface-900 flex items-center gap-2 rounded border p-1.5">
                    <img
                      src={image.previewUrl}
                      alt="Attached screenshot"
                      className="h-10 w-14 shrink-0 rounded-sm object-cover"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-surface-100 truncate text-[12px]">{image.name}</div>
                      <div className="text-surface-500 text-[11px]">
                        {formatImageSize(image.size)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setImage(null)}
                      aria-label="Remove screenshot"
                      title="Remove screenshot"
                      className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none"
                    >
                      <LuX size={13} />
                    </button>
                  </div>
                ) : (
                  <div
                    onDragOver={(event) => {
                      event.preventDefault();
                      setIsDraggingImage(true);
                    }}
                    onDragLeave={() => setIsDraggingImage(false)}
                    onDrop={handleDrop}
                    className={clsx(
                      "flex items-center gap-2 rounded border border-dashed px-2 py-1.5 text-[12px] transition-colors",
                      isDraggingImage ? "border-accent-400 bg-accent-600/10" : "border-surface-600",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isPreparingImage}
                      className="text-surface-200 hover:text-surface-50 flex shrink-0 items-center gap-1.5 rounded px-1 py-0.5 font-medium outline-none disabled:opacity-50"
                    >
                      {isPreparingImage ? (
                        <LuLoaderCircle size={14} className="animate-spin" />
                      ) : (
                        <LuImagePlus size={14} />
                      )}
                      {isPreparingImage ? "Preparing…" : "Attach screenshot"}
                    </button>
                    <span className="text-surface-500 min-w-0 truncate text-[11px]">
                      or drop / paste an image · optional
                    </span>
                  </div>
                )}
                {imageError && (
                  <p role="alert" className="text-danger-400 text-[11px]">
                    {imageError}
                  </p>
                )}
              </div>

              <label className="text-surface-300 mt-3 flex items-center gap-2 text-[12px]">
                <input
                  type="checkbox"
                  checked={includePage}
                  onChange={(event) => update({ includePage: event.target.checked })}
                  className="accent-accent-600"
                />
                <span className="min-w-0 truncate">
                  Include current page{" "}
                  <span className="text-surface-500 font-mono text-[11px]">{location}</span>
                </span>
              </label>

              {/* Honeypot: off-screen and skipped by keyboard and autofill, so
                  only bots fill it in. */}
              <input
                type="text"
                name="website"
                value={website}
                onChange={(event) => setWebsite(event.target.value)}
                tabIndex={-1}
                autoComplete="off"
                aria-hidden
                className="absolute -left-[9999px] h-px w-px opacity-0"
              />

              {error && (
                <p role="alert" className="text-danger-400 mt-3 text-[12px]">
                  {error}
                </p>
              )}

              <div className="mt-5 flex justify-end gap-2">
                <Dialog.Close
                  type="button"
                  className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 h-8 rounded px-3 text-[12px] font-medium outline-none"
                >
                  Cancel
                </Dialog.Close>
                <button
                  type="submit"
                  disabled={!canSend}
                  aria-busy={isSending}
                  className="bg-accent-600 hover:bg-accent-500 h-8 rounded px-3 text-[12px] font-medium text-white outline-none disabled:opacity-50"
                >
                  {/* Both labels share one grid cell, so the button keeps the
                      wider one's width and doesn't jump while sending. */}
                  <span className="grid">
                    <span className={clsx("col-start-1 row-start-1", isSending && "invisible")}>
                      Send Feedback
                    </span>
                    <span
                      className={clsx(
                        "col-start-1 row-start-1 flex items-center justify-center gap-1.5",
                        !isSending && "invisible",
                      )}
                    >
                      <LuLoaderCircle size={13} className="animate-spin" />
                      Sending…
                    </span>
                  </span>
                </button>
              </div>
            </form>
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Plain header icon button + dialog, for page headers outside the project toolbar. */
export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-7 w-7 items-center justify-center rounded transition-colors"
        aria-label="Send feedback"
        title="Send feedback"
      >
        <LuMessageSquareText size={15} />
      </button>
      <FeedbackDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
