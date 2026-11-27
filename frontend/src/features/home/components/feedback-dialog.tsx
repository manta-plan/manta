import { useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useLocation } from "wouter";
import clsx from "clsx";
import {
  LuCircleCheck,
  LuCrop,
  LuLoaderCircle,
  LuMessageSquareText,
  LuPencil,
  LuX,
} from "react-icons/lu";
import { sendFeedback, type FeedbackCategory } from "../lib/send-feedback";
import { FeedbackImageError, prepareFeedbackImage } from "../lib/feedback-image";
import { captureRegion, type Rect } from "../lib/capture-region";
import { RegionSelector } from "./region-selector";
import { ScreenshotEditor } from "./screenshot-editor";
import { ApiError } from "../../../api/manta";
import { useFeedbackDraft } from "../lib/feedback-draft";
import { useZoomPan } from "../../../utils/useZoomPan";

/** The backend's limit on a message. */
const MAX_MESSAGE_LENGTH = 2000;

const CATEGORIES: { value: FeedbackCategory; label: string; placeholder: string }[] = [
  {
    value: "bug_report",
    label: "Bug report",
    placeholder: "What happened, and what did you expect instead?",
  },
  {
    value: "feature_request",
    label: "Feature request",
    placeholder: "What would you like Manta to do?",
  },
  {
    value: "pain_point",
    label: "Pain point",
    placeholder: "What is hard, slow or confusing?",
  },
  { value: "question", label: "Question", placeholder: "What would you like to know?" },
];

// The backend adds the username and files it in the team's feedback sheet.
export function FeedbackDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [location] = useLocation();
  const { category, message, includePage, image, update, setImage, clear } = useFeedbackDraft();
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSent, setIsSent] = useState(false);
  const [isPreparingImage, setIsPreparingImage] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  // While the snip overlay or editor is up, the dialog hides and must ignore
  // the outside-press / Escape closes they would otherwise trigger.
  const overlayActive = isSelecting || isEditing;

  const activeCategory = CATEGORIES.find((c) => c.value === category) ?? CATEGORIES[0];
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

  const handleSelect = async (rect: Rect) => {
    setIsSelecting(false);
    setImageError(null);
    setIsPreparingImage(true);
    try {
      // Let the overlay unmount before the page is rendered.
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      setImage(await prepareFeedbackImage(await captureRegion(rect)));
    } catch (err) {
      setImageError(
        err instanceof FeedbackImageError ? err.message : "Couldn't capture the screen.",
      );
    } finally {
      setIsPreparingImage(false);
    }
  };

  const submit = async () => {
    if (!canSend) return;
    setIsSending(true);
    setError(null);
    try {
      await sendFeedback({
        category,
        message: message.trim(),
        page: includePage ? location : "",
        screenshot: image?.base64,
      });
      setIsSent(true);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? /screenshot/i.test(err.message)
            ? "The screenshot couldn't be sent. Remove it or take another."
            : `Your feedback was rejected. Keep the message under ${MAX_MESSAGE_LENGTH} characters.`
          : "Couldn't send your feedback. Check your connection and try again.",
      );
    } finally {
      setIsSending(false);
    }
  };

  const handleOpenChange = (next: boolean) => {
    if (!next && overlayActive) return;
    onOpenChange(next);
    if (!next) {
      // The draft stays so the dialog can be reopened to carry on; only a
      // sent message is cleared.
      if (isSent) clear();
      setError(null);
      setIsSent(false);
      setImageError(null);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange} modal={!overlayActive}>
      <Dialog.Portal>
        <Dialog.Backdrop
          data-capture-exclude
          className={clsx("fixed inset-0 z-40 bg-black/50", overlayActive && "invisible")}
        />
        <Dialog.Popup
          data-capture-exclude
          className={clsx(
            "border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 w-[440px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl shadow-black/50 outline-none",
            overlayActive && "invisible",
          )}
        >
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

              <label className="flex flex-col gap-1">
                <span className="text-surface-400 text-[11px] font-medium">Category</span>
                <select
                  value={category}
                  onChange={(event) => update({ category: event.target.value as FeedbackCategory })}
                  className="border-surface-600 bg-surface-900 text-surface-50 focus:border-accent-500 h-9 rounded border px-2 text-[13px] outline-none"
                >
                  {CATEGORIES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="mt-4 flex flex-col gap-1">
                <span className="text-surface-400 text-[11px] font-medium">Message</span>
                <textarea
                  value={message}
                  onChange={(event) => update({ message: event.target.value })}
                  placeholder={activeCategory.placeholder}
                  maxLength={MAX_MESSAGE_LENGTH}
                  rows={5}
                  autoFocus
                  className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 resize-none rounded border px-2 py-1.5 text-[13px] outline-none"
                />
                <span className="text-surface-500 text-[11px]">
                  Please don't include personal data, such as names, email addresses or passwords,
                  in your message or screenshot.
                </span>
              </label>

              <div className="mt-3 flex flex-col gap-1">
                {image ? (
                  <div className="border-surface-600 bg-surface-900 relative h-48 overflow-hidden rounded border p-1.5">
                    {/* The key refits it for every new or re-edited image. */}
                    <ZoomPanImage
                      key={image.previewUrl}
                      src={image.previewUrl}
                      alt="Attached screenshot"
                    />
                    <div className="absolute top-2.5 right-2.5 z-10 flex gap-1">
                      <button
                        type="button"
                        onClick={() => setIsEditing(true)}
                        aria-label="Edit screenshot"
                        title="Edit screenshot"
                        className="flex h-6 w-6 items-center justify-center rounded bg-black/60 text-white outline-none hover:bg-black/80"
                      >
                        <LuPencil size={13} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setImage(null)}
                        aria-label="Remove screenshot"
                        title="Remove screenshot"
                        className="flex h-6 w-6 items-center justify-center rounded bg-black/60 text-white outline-none hover:bg-black/80"
                      >
                        <LuX size={13} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="border-surface-600 flex items-center gap-2 rounded border border-dashed px-2 py-1.5 text-[12px]">
                    <button
                      type="button"
                      onClick={() => setIsSelecting(true)}
                      disabled={isPreparingImage}
                      className="text-surface-200 hover:text-surface-50 flex shrink-0 items-center gap-1.5 rounded px-1 py-0.5 font-medium outline-none disabled:opacity-50"
                    >
                      {isPreparingImage ? (
                        <LuLoaderCircle size={14} className="animate-spin" />
                      ) : (
                        <LuCrop size={14} />
                      )}
                      {isPreparingImage ? "Preparing…" : "Take a Screen Shot"}
                    </button>
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
      {isSelecting && (
        <RegionSelector
          onSelect={(rect) => void handleSelect(rect)}
          onCancel={() => setIsSelecting(false)}
        />
      )}
      {isEditing && image && (
        <ScreenshotEditor
          src={image.previewUrl}
          onCancel={() => setIsEditing(false)}
          onDone={(file) => {
            setIsEditing(false);
            void attachImage(file);
          }}
        />
      )}
    </Dialog.Root>
  );
}

/** Fitted on load; wheel zooms, drag pans, double-click resets. */
function ZoomPanImage({ src, alt }: { src: string; alt: string }) {
  const { ref, handlers, contentStyle } = useZoomPan<HTMLDivElement>({ maxScale: 6 });
  return (
    <div
      ref={ref}
      {...handlers}
      className="h-full w-full cursor-grab touch-none overflow-hidden select-none active:cursor-grabbing"
    >
      <img
        src={src}
        alt={alt}
        draggable={false}
        style={contentStyle}
        className="h-full w-full rounded-sm object-contain"
      />
    </div>
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
