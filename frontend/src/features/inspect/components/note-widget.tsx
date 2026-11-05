import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LuCheck, LuCopy, LuPencilLine, LuStickyNote, LuX } from "react-icons/lu";
import { useWidgetItem } from "../../project/lib/widget-set-context";
import type { NoteItem } from "../../project/lib/widget-sets";
import { AddToMenu } from "./add-to-menu";
import { WidgetIconButton } from "./widget-icon-button";
import { WidgetDragHandle } from "./widget-reorder";

// Text the user writes onto an inspection page, in Markdown. It shows
// formatted, and grows with its text rather than taking a chart's height.
export function NoteWidget({
  item,
  onChange,
  onDuplicate,
  startsEditing,
}: {
  item: NoteItem;
  onChange: (text: string) => void;
  onDuplicate: () => void;
  startsEditing: boolean;
}) {
  const widgetItem = useWidgetItem();
  const [isEditing, setEditing] = useState(startsEditing || item.text.trim() === "");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // The editor grows with the text, like the note it becomes.
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [isEditing, item.text]);

  // Focus only when the user opens the editor, or just added the note; an
  // empty saved note opens in edit mode without pulling focus on page load.
  const shouldFocus = useRef(startsEditing);
  useEffect(() => {
    if (isEditing && shouldFocus.current) textareaRef.current?.focus();
    shouldFocus.current = true;
  }, [isEditing]);

  return (
    <section className="group border-surface-700 bg-surface-900 w-full shrink-0 border px-4 py-3">
      <div className="flex items-start gap-3">
        <div className="-ml-1 flex shrink-0 items-center gap-1">
          <WidgetDragHandle />
          <LuStickyNote size={14} className="text-surface-500 shrink-0" />
        </div>
        <div className="min-w-0 flex-1">
          {isEditing ? (
            <>
              <textarea
                ref={textareaRef}
                value={item.text}
                onChange={(event) => onChange(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Escape" ||
                    (event.key === "Enter" && (event.metaKey || event.ctrlKey))
                  ) {
                    event.preventDefault();
                    setEditing(false);
                  }
                }}
                rows={4}
                placeholder={
                  "Write a note in Markdown: ## headings, **bold**, - lists, [links](https://…)"
                }
                aria-label="Note text"
                className="border-surface-600 bg-surface-950 text-surface-100 placeholder:text-surface-500 focus-visible:border-accent-500 min-h-24 w-full resize-none overflow-hidden rounded border p-2 font-mono text-[12px] leading-5 outline-none"
              />
              <div className="text-surface-500 mt-1 text-[11px]">
                Markdown · ⌘↵ or Esc to finish
              </div>
            </>
          ) : (
            // Double-click the text to edit it.
            <div onDoubleClick={() => setEditing(true)} className="note-content min-w-0">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ children, href }) => (
                    <a href={href} target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  ),
                }}
              >
                {item.text}
              </ReactMarkdown>
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <WidgetIconButton
            icon={isEditing ? LuCheck : LuPencilLine}
            label={isEditing ? "Done" : "Edit note"}
            onClick={() => setEditing((editing) => !editing)}
          />
          <WidgetIconButton
            icon={LuCopy}
            label="Duplicate widget"
            ariaLabel="Duplicate note"
            onClick={onDuplicate}
          />
          <AddToMenu widgetName="Note" />
          {widgetItem && (
            <WidgetIconButton
              icon={LuX}
              label="Remove widget"
              ariaLabel="Remove note"
              onClick={widgetItem.onRemove}
            />
          )}
        </div>
      </div>
    </section>
  );
}
