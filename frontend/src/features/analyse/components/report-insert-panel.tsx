// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useContext, useEffect, useMemo, useRef, useState } from "react";
import type { IconType } from "react-icons";
import {
  LuChartColumn,
  LuChevronDown,
  LuChevronRight,
  LuCircle,
  LuHeading,
  LuImage,
  LuMinus,
  LuSearch,
  LuSlash,
  LuSquare,
  LuText,
} from "react-icons/lu";
import type { BlockContent, Report, ReportBlock } from "../data/reports";
import { lastUsedResultId, placeBlock } from "../lib/report-blocks";
import { prepareReportImage, REPORT_IMAGE_TYPES, ReportImageError } from "../lib/report-image";
import { insertableWidgetGroups, type InsertableWidget } from "../lib/report-widget-refs";
import { ResultCatalogueContext } from "../lib/use-result-data";
import { useProjectStore } from "../../project/store/project-store";

const CONTENT_ITEMS: {
  key: string;
  label: string;
  icon: IconType;
  content: BlockContent | null;
}[] = [
  {
    key: "heading",
    label: "Heading",
    icon: LuHeading,
    content: { kind: "heading", text: "Heading", level: 1 },
  },
  {
    key: "text",
    label: "Text",
    icon: LuText,
    content: { kind: "text", text: "Write here. **Markdown** works." },
  },
  { key: "divider", label: "Divider", icon: LuMinus, content: { kind: "divider" } },
  { key: "image", label: "Image", icon: LuImage, content: null },
  {
    key: "rectangle",
    label: "Rectangle",
    icon: LuSquare,
    content: { kind: "shape", shape: "rectangle" },
  },
  {
    key: "ellipse",
    label: "Ellipse",
    icon: LuCircle,
    content: { kind: "shape", shape: "ellipse" },
  },
  { key: "line", label: "Line", icon: LuSlash, content: { kind: "shape", shape: "line" } },
];

/**
 * Adds blocks to the report: its own text, images and shapes, and the
 * widgets of the built-in and the user's inspections. A click places the
 * block in the first free spot, on the page the selected block is on (or the
 * first page), and selects it.
 */
export function ReportInsertPanel({
  report,
  selectedPageId,
  onAdd,
}: {
  report: Report;
  selectedPageId: string | null;
  onAdd: (pageId: string, block: ReportBlock) => void;
}) {
  const catalogue = useContext(ResultCatalogueContext);
  const inspections = useProjectStore((s) => s.inspections);
  const [query, setQuery] = useState("");
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set(["system-overview"]));
  const [message, setMessage] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  // A message is about the last insert: it goes when the pages change (a page added, a block moved) or after a while.
  const layoutKey = report.pages.map((page) => `${page.id}:${page.blocks.length}`).join("|");
  useEffect(() => setMessage(null), [layoutKey]);
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(null), 5000);
    return () => clearTimeout(timer);
  }, [message]);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return insertableWidgetGroups(inspections)
      .map((group) => ({
        ...group,
        widgets: needle
          ? group.widgets.filter((widget) =>
              `${widget.label} ${group.name}`.toLowerCase().includes(needle),
            )
          : group.widgets,
      }))
      .filter((group) => group.widgets.length > 0);
  }, [inspections, query]);
  const contentItems = CONTENT_ITEMS.filter((item) =>
    item.label.toLowerCase().includes(query.trim().toLowerCase()),
  );

  const add = (content: BlockContent, from: Report = report) => {
    const placement = placeBlock(from, content, selectedPageId);
    if (!placement) {
      setMessage(
        `No free spot on ${selectedPageId ? "this page" : "the pages"} is big enough for it. Add a page, or make space.`,
      );
      return;
    }
    setMessage(null);
    onAdd(placement.pageId, placement.block);
  };
  const addWidget = (widget: InsertableWidget) => {
    const resultId = lastUsedResultId(report) ?? catalogue?.results[0]?.id;
    if (resultId) add({ kind: "widget", ref: widget.ref, resultId });
  };
  const addImage = async (file: File) => {
    try {
      const { src, name } = await prepareReportImage(file);
      // Preparing the image takes a moment, in which other blocks may have been added: place it on the report as it is now.
      const current = useProjectStore.getState().reports.find((item) => item.id === report.id);
      add({ kind: "image", src, alt: name }, current ?? report);
    } catch (error) {
      setMessage(error instanceof ReportImageError ? error.message : "Couldn't add that image.");
    }
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="border-surface-600/60 shrink-0 border-b p-3">
        <label className="relative block">
          <LuSearch
            size={13}
            className="text-surface-500 pointer-events-none absolute top-1/2 left-2 -translate-y-1/2"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search blocks and widgets"
            aria-label="Search blocks and widgets"
            className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 h-8 w-full rounded border pr-2 pl-7 text-[12px] outline-none"
          />
        </label>
        <input
          ref={fileInput}
          type="file"
          accept={REPORT_IMAGE_TYPES.join(",")}
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            // Reset so picking the same file again still fires onChange.
            event.target.value = "";
            if (file) void addImage(file);
          }}
        />
      </div>
      {/* Over the list, not in it, so the buttons don't move under the pointer. */}
      {message && (
        <p
          role="alert"
          className="border-danger-500/50 bg-surface-900/95 text-surface-100 absolute inset-x-3 bottom-3 z-10 rounded border px-2 py-1.5 text-[11px] leading-4 shadow-lg backdrop-blur"
        >
          {message}
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {contentItems.length > 0 && (
          <section>
            <h3 className="text-surface-400 mb-1.5 text-[11px] font-medium">Content</h3>
            <div className="grid grid-cols-2 gap-1.5">
              {contentItems.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => (item.content ? add(item.content) : fileInput.current?.click())}
                    className="border-surface-600 bg-surface-900 text-surface-200 hover:border-surface-500 hover:text-surface-50 focus-visible:border-accent-500 flex h-8 items-center gap-2 rounded border px-2 text-[12px] outline-none"
                  >
                    <Icon size={14} className="text-surface-400 shrink-0" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        <section className={contentItems.length > 0 ? "mt-4" : ""}>
          <h3 className="text-surface-400 mb-1.5 text-[11px] font-medium">Inspect widgets</h3>
          {!catalogue && (
            <p className="text-surface-500 mb-2 text-[11px]">Loading the record's results…</p>
          )}
          {groups.length === 0 && (
            <p className="text-surface-500 text-[11px]">No widget matches.</p>
          )}
          {groups.map((group) => {
            const isOpen = query.trim() !== "" || openGroups.has(group.id);
            return (
              <div key={group.id} className="mb-1">
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() =>
                    setOpenGroups((current) => {
                      const next = new Set(current);
                      if (next.has(group.id)) next.delete(group.id);
                      else next.add(group.id);
                      return next;
                    })
                  }
                  className="text-surface-200 hover:bg-surface-700/60 focus-visible:bg-surface-700/60 flex h-7 w-full items-center gap-1.5 rounded px-1 text-left text-[12px] font-medium outline-none"
                >
                  {isOpen ? (
                    <LuChevronDown size={12} className="text-surface-400 shrink-0" />
                  ) : (
                    <LuChevronRight size={12} className="text-surface-400 shrink-0" />
                  )}
                  <span className="truncate">{group.name}</span>
                  <span className="text-surface-500 ml-auto shrink-0 text-[11px] font-normal">
                    {group.widgets.length}
                  </span>
                </button>
                {isOpen &&
                  group.widgets.map((widget) => (
                    <button
                      key={widget.key}
                      type="button"
                      disabled={!catalogue}
                      onClick={() => addWidget(widget)}
                      className="text-surface-300 hover:bg-surface-700/60 hover:text-surface-50 focus-visible:bg-surface-700/60 flex h-7 w-full items-center gap-2 rounded pr-1 pl-6 text-left text-[12px] outline-none disabled:opacity-50"
                    >
                      <LuChartColumn size={12} className="text-accent-400 shrink-0" />
                      <span className="truncate">{widget.label}</span>
                    </button>
                  ))}
              </div>
            );
          })}
        </section>
      </div>
    </div>
  );
}
