// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import clsx from "clsx";
import type { Report, ReportBlock } from "../data/reports";
import type { ReportTheme } from "../data/report-themes";
import type { EditOptions } from "../lib/report-history";
import { ReportBlockInspector } from "./report-block-inspector";
import { ReportInsertPanel } from "./report-insert-panel";
import { ReportThemePanel } from "./report-theme-panel";

type Tab = "insert" | "block" | "theme";

/**
 * The report's side panel: Insert adds blocks, Block sets the selected one's
 * options, Theme sets the report's look. Selecting a block opens Block, and
 * clearing the selection goes back to Insert; the tabs let you switch by hand
 * in between.
 */
export function ReportSidePanel({
  report,
  selectedBlock,
  selectedPageId,
  onAdd,
  onUpdate,
  onDuplicate,
  onRemove,
  onThemeChange,
}: {
  report: Report;
  selectedBlock: ReportBlock | null;
  selectedPageId: string | null;
  onAdd: (pageId: string, block: ReportBlock) => void;
  onUpdate: (update: (block: ReportBlock) => ReportBlock, options?: EditOptions) => void;
  onDuplicate: () => void;
  onRemove: () => void;
  onThemeChange: (theme: ReportTheme) => void;
}) {
  const [tab, setTab] = useState<Tab>("insert");
  const selectedId = selectedBlock?.id ?? null;
  useEffect(() => setTab(selectedId ? "block" : "insert"), [selectedId]);
  const page = report.pages.find((candidate) => candidate.id === selectedPageId);
  const showBlock = tab === "block" && selectedBlock && page;

  return (
    <aside className="border-surface-600 bg-surface-800 flex w-72 shrink-0 flex-col border-l">
      <div
        role="tablist"
        className="border-surface-600/60 flex h-9 shrink-0 items-stretch border-b px-2"
      >
        {(["insert", "block", "theme"] as const).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            data-tour={`report-tab-${id}`}
            aria-selected={tab === id}
            disabled={id === "block" && !selectedBlock}
            onClick={() => setTab(id)}
            className={clsx(
              "px-3 text-[11px] font-semibold uppercase tracking-wide outline-none disabled:opacity-40",
              tab === id
                ? "border-b-2 border-accent-500 text-surface-50"
                : "border-b-2 border-transparent text-surface-400 hover:text-surface-100",
            )}
          >
            {id === "insert" ? "Insert" : id === "block" ? "Block" : "Theme"}
          </button>
        ))}
      </div>
      {tab === "theme" ? (
        <ReportThemePanel theme={report.theme} onChange={onThemeChange} />
      ) : showBlock ? (
        <ReportBlockInspector
          report={report}
          page={page}
          block={selectedBlock}
          onUpdate={onUpdate}
          onDuplicate={onDuplicate}
          onRemove={onRemove}
        />
      ) : (
        <ReportInsertPanel report={report} selectedPageId={selectedPageId} onAdd={onAdd} />
      )}
    </aside>
  );
}
