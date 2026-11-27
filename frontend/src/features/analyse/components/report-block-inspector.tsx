// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useContext, useEffect, useRef, useState, type ReactNode } from "react";
import clsx from "clsx";
import { LuCopy, LuImage, LuTrash2, LuUnlink } from "react-icons/lu";
import type { BlockContent, BlockRect, Report, ReportBlock, ReportPage } from "../data/reports";
import type { EditOptions } from "../lib/report-history";
import { isFree, minBlockSize, pageMetrics } from "../lib/report-layout";
import { prepareReportImage, REPORT_IMAGE_TYPES, ReportImageError } from "../lib/report-image";
import { detachedRef, widgetRefLabel, widgetRefSource } from "../lib/report-widget-refs";
import { ResultCatalogueContext } from "../lib/use-result-data";
import { useProjectStore } from "../../project/store/project-store";
import { FormSelect } from "../../../components/form-select";

const KIND_LABEL: Record<BlockContent["kind"], string> = {
  widget: "Widget",
  heading: "Heading",
  text: "Text",
  divider: "Divider",
  image: "Image",
  shape: "Shape",
};

const inputClass =
  "h-8 w-full rounded border border-surface-600 bg-surface-900 px-2 text-[12px] text-surface-50 outline-none placeholder:text-surface-500 focus:border-accent-500";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-surface-400 text-[11px] font-medium">{label}</span>
      {children}
    </label>
  );
}

function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-col gap-1">
      <span className="text-surface-400 text-[11px] font-medium">{label}</span>
      <div
        className="grid gap-1.5"
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={option.value === value}
            onClick={() => onChange(option.value)}
            className={clsx(
              "h-8 rounded border text-[12px] font-medium outline-none",
              option.value === value
                ? "border-accent-500 bg-accent-600/15 text-surface-50"
                : "border-surface-600 bg-surface-900 text-surface-300 hover:border-surface-500 hover:text-surface-100",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Position and size in grid cells; a value that would leave the page, shrink the block too far or overlap another isn't applied. */
function LayoutFields({
  block,
  page,
  report,
  onRect,
}: {
  block: ReportBlock;
  page: ReportPage;
  report: Report;
  onRect: (rect: BlockRect) => void;
}) {
  const metrics = pageMetrics(report.page);
  const min = minBlockSize(block.content);
  const [draft, setDraft] = useState<Record<keyof BlockRect, string>>(() => toStrings(block.rect));
  // Follows the block when it's moved some other way, by dragging for instance.
  useEffect(() => setDraft(toStrings(block.rect)), [block.rect]);

  const change = (key: keyof BlockRect, text: string) => {
    const next = { ...draft, [key]: text };
    setDraft(next);
    const rect = { x: Number(next.x), y: Number(next.y), w: Number(next.w), h: Number(next.h) };
    if (isValid(rect)) onRect(rect);
  };
  const isValid = (rect: BlockRect) =>
    Object.values(rect).every(Number.isInteger) &&
    rect.x >= 0 &&
    rect.y >= 0 &&
    rect.w >= min.w &&
    rect.h >= min.h &&
    rect.x + rect.w <= metrics.columns &&
    rect.y + rect.h <= metrics.rows &&
    isFree(rect, page.blocks, block.id);
  const isDraftValid = isValid({
    x: Number(draft.x),
    y: Number(draft.y),
    w: Number(draft.w),
    h: Number(draft.h),
  });

  const fields: { key: keyof BlockRect; label: string }[] = [
    { key: "x", label: "X" },
    { key: "y", label: "Y" },
    { key: "w", label: "Width" },
    { key: "h", label: "Height" },
  ];
  return (
    <div>
      <div className="text-surface-400 mb-1 text-[11px] font-medium">Position and size (cells)</div>
      <div className="grid grid-cols-2 gap-2">
        {fields.map((field) => (
          <label key={field.key} className="text-surface-400 flex items-center gap-2 text-[11px]">
            <span className="w-9 shrink-0">{field.label}</span>
            <input
              type="number"
              min={0}
              value={draft[field.key]}
              onChange={(event) => change(field.key, event.target.value)}
              aria-invalid={!isDraftValid}
              className={clsx(inputClass, "tabular-nums", !isDraftValid && "border-danger-500")}
            />
          </label>
        ))}
      </div>
      <p
        className={clsx("mt-1 text-[11px]", isDraftValid ? "text-surface-500" : "text-danger-400")}
      >
        {isDraftValid
          ? `The page is ${metrics.columns} cells wide and ${metrics.rows} tall.`
          : "That would leave the page, be too small or overlap another block."}
      </p>
    </div>
  );
}

const toStrings = (rect: BlockRect) => ({
  x: String(rect.x),
  y: String(rect.y),
  w: String(rect.w),
  h: String(rect.h),
});

/** The selected block's settings: what it shows, and where it sits. */
export function ReportBlockInspector({
  report,
  page,
  block,
  onUpdate,
  onDuplicate,
  onRemove,
}: {
  report: Report;
  page: ReportPage;
  block: ReportBlock;
  onUpdate: (update: (block: ReportBlock) => ReportBlock, options?: EditOptions) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}) {
  const catalogue = useContext(ResultCatalogueContext);
  const inspections = useProjectStore((s) => s.inspections);
  const fileInput = useRef<HTMLInputElement>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const { content } = block;
  // Typing into a field is one undo step, not one per letter.
  const setContent = (patch: Partial<BlockContent>) =>
    onUpdate(
      (current) => ({ ...current, content: { ...current.content, ...patch } as BlockContent }),
      { label: "Edit block", mergeKey: `content:${block.id}:${Object.keys(patch).join()}` },
    );

  const replaceImage = async (file: File) => {
    try {
      const { src, name } = await prepareReportImage(file);
      setImageError(null);
      setContent({ src, alt: name });
    } catch (error) {
      setImageError(error instanceof ReportImageError ? error.message : "Couldn't use that image.");
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-surface-600/60 flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2">
        <div className="text-surface-100 min-w-0 truncate text-[12px] font-medium">
          {KIND_LABEL[content.kind]} block
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            aria-label="Duplicate block"
            title="Duplicate (Ctrl/Cmd+D)"
            onClick={onDuplicate}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-7 w-7 items-center justify-center rounded outline-none"
          >
            <LuCopy size={13} />
          </button>
          <button
            type="button"
            aria-label="Delete block"
            title="Delete (Delete)"
            onClick={onRemove}
            className="text-surface-300 hover:bg-surface-700 hover:text-danger-400 flex h-7 w-7 items-center justify-center rounded outline-none"
          >
            <LuTrash2 size={13} />
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        {content.kind === "widget" && (
          <>
            <div>
              <div className="text-surface-400 text-[11px] font-medium">Widget</div>
              {widgetRefLabel(content.ref, inspections) ? (
                <>
                  <div className="text-surface-100 mt-1 text-[12px]">
                    {widgetRefLabel(content.ref, inspections)}
                  </div>
                  <div className="text-surface-500 text-[11px]">
                    {content.ref.source === "detached"
                      ? "A copy owned by this report. Changes to the view don't reach it."
                      : content.ref.source === "built-in"
                        ? "Built-in widget"
                        : `From ${widgetRefSource(content.ref, inspections)}, kept in step with it`}
                  </div>
                  {content.ref.source === "inspection" && (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          const copy = detachedRef(content.ref, inspections);
                          if (copy) setContent({ ref: copy });
                        }}
                        className="border-surface-600 bg-surface-900 text-surface-200 hover:border-surface-500 hover:text-surface-50 mt-2 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] outline-none"
                      >
                        <LuUnlink size={12} />
                        Detach from the view
                      </button>
                      <p className="text-surface-500 mt-1 text-[11px] leading-4">
                        Keeps this widget as it is now, even if it's edited or deleted in the view.
                      </p>
                    </>
                  )}
                </>
              ) : (
                <div className="text-danger-400 mt-1 text-[11px]">
                  This widget no longer exists. Delete the block.
                </div>
              )}
            </div>
            <Field label="Run result">
              <FormSelect
                value={content.resultId}
                onValueChange={(resultId) => setContent({ resultId })}
                options={(catalogue?.results ?? []).map((run) => ({
                  value: run.id,
                  label: run.label,
                }))}
                disabled={!catalogue}
                placeholder="Select run result"
              />
            </Field>
            <Field label="Title">
              <input
                value={content.title ?? ""}
                onChange={(event) => setContent({ title: event.target.value || undefined })}
                placeholder="The widget's own title"
                className={inputClass}
              />
            </Field>
          </>
        )}

        {content.kind === "heading" && (
          <>
            <Field label="Text">
              <input
                value={content.text}
                onChange={(event) => setContent({ text: event.target.value })}
                className={inputClass}
              />
            </Field>
            <Segmented
              label="Level"
              value={content.level}
              options={[
                { value: 1, label: "Large" },
                { value: 2, label: "Medium" },
                { value: 3, label: "Small" },
              ]}
              onChange={(level) => setContent({ level })}
            />
          </>
        )}

        {content.kind === "text" && (
          <Field label="Text (Markdown)">
            <textarea
              value={content.text}
              onChange={(event) => setContent({ text: event.target.value })}
              rows={8}
              className="border-surface-600 bg-surface-900 text-surface-50 focus:border-accent-500 resize-y rounded border p-2 font-mono text-[12px] leading-5 outline-none"
            />
          </Field>
        )}

        {content.kind === "image" && (
          <>
            <img
              src={content.src}
              alt={content.alt}
              className="border-surface-600 bg-surface-900 h-24 w-full rounded border object-contain"
            />
            <input
              ref={fileInput}
              type="file"
              accept={REPORT_IMAGE_TYPES.join(",")}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void replaceImage(file);
              }}
            />
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="border-surface-600 bg-surface-900 text-surface-200 hover:border-surface-500 hover:text-surface-50 flex h-8 items-center justify-center gap-1.5 rounded border text-[12px] font-medium outline-none"
            >
              <LuImage size={13} />
              Replace image
            </button>
            {imageError && (
              <p role="alert" className="text-danger-400 text-[11px]">
                {imageError}
              </p>
            )}
            <Field label="Alt text">
              <input
                value={content.alt}
                onChange={(event) => setContent({ alt: event.target.value })}
                placeholder="Describe the image"
                className={inputClass}
              />
            </Field>
          </>
        )}

        {content.kind === "shape" && (
          <Segmented
            label="Shape"
            value={content.shape}
            options={[
              { value: "rectangle", label: "Rectangle" },
              { value: "ellipse", label: "Ellipse" },
              { value: "line", label: "Line" },
            ]}
            onChange={(shape) => setContent({ shape })}
          />
        )}

        <LayoutFields
          block={block}
          page={page}
          report={report}
          onRect={(rect) =>
            onUpdate((current) => ({ ...current, rect }), {
              label: "Move or resize block",
              mergeKey: `rect:${block.id}`,
            })
          }
        />
      </div>
    </div>
  );
}
