// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  LuCalendarClock,
  LuChartBar,
  LuFileDown,
  LuGrid3X3,
  LuLoaderCircle,
  LuMaximize,
  LuPlus,
  LuRedo2,
  LuTrash2,
  LuUndo2,
  LuZoomIn,
  LuZoomOut,
} from "react-icons/lu";
import { useProjectStore } from "../../project/store/project-store";
import { pageSetupLabel, type Report, type ReportBlock } from "../data/reports";
import { duplicateBlock } from "../lib/report-blocks";
import type { EditOptions } from "../lib/report-history";
import { pageMetrics } from "../lib/report-layout";
import { ResultCatalogueContext, useLoadResultCatalogue } from "../lib/use-result-data";
import { useElementSize } from "../../project/lib/use-element-size";
import { ConfirmDialog } from "../../../components/confirm-dialog";
import { ReportPageView } from "./report-page-view";
import { ReportPrintRoot } from "./report-print-root";
import { ReportSidePanel } from "./report-side-panel";
import type { WidgetsStatus } from "./report-block-view";

const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5];
/** Room kept around the pages in the scroll area. */
const DESK_PADDING = 24;

function ViewButton({
  label,
  onClick,
  active = false,
  disabled = false,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={`flex h-7 w-7 items-center justify-center rounded outline-none disabled:opacity-40 ${
        active
          ? "bg-accent-600/25 text-accent-300"
          : "text-surface-300 hover:bg-surface-700 hover:text-surface-50"
      }`}
    >
      {children}
    </button>
  );
}

// The selected report: its pages on paper, to scale, with the blocks laid
// out by hand on each page's grid.
export function ReportDashboard() {
  const report = useProjectStore((s) => s.reports.find((r) => r.id === s.selectedReportId));
  // Keyed, so the selection and zoom don't carry over to another report.
  return report ? <ReportWorkspace key={report.id} report={report} /> : null;
}

function ReportWorkspace({ report }: { report: Report }) {
  const catalogueState = useLoadResultCatalogue();
  const updateReportBlocks = useProjectStore((s) => s.updateReportBlocks);
  const addReportPage = useProjectStore((s) => s.addReportPage);
  const removeReportPage = useProjectStore((s) => s.removeReportPage);
  const setReportTheme = useProjectStore((s) => s.setReportTheme);
  const undoReport = useProjectStore((s) => s.undoReport);
  const redoReport = useProjectStore((s) => s.redoReport);
  const history = useProjectStore((s) => s.reportHistory[report.id]);
  const undoStep = history?.past[history.past.length - 1];
  const redoStep = history?.future[history.future.length - 1];
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [pageToRemove, setPageToRemove] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const finishExport = useCallback(() => setIsExporting(false), []);
  const [deskRef, deskSize] = useElementSize<HTMLDivElement>();
  // 'fit' shows a page across the window, never larger than life.
  const [zoom, setZoom] = useState<"fit" | number>("fit");
  const [showGrid, setShowGrid] = useState(false);

  const metrics = pageMetrics(report.page);
  const fitScale =
    deskSize.width > 0 ? Math.min(1, (deskSize.width - 2 * DESK_PADDING) / metrics.width) : 1;
  const scale = zoom === "fit" ? fitScale : zoom;
  const stepZoom = (direction: -1 | 1) => {
    const next =
      direction === 1
        ? ZOOM_STEPS.find((step) => step > scale + 0.001)
        : [...ZOOM_STEPS].reverse().find((step) => step < scale - 0.001);
    if (next !== undefined) setZoom(next);
  };
  const pageCount = report.pages.length;
  const selectedPage =
    report.pages.find((page) => page.blocks.some((block) => block.id === selectedBlockId)) ?? null;
  const selectedBlock = selectedPage?.blocks.find((block) => block.id === selectedBlockId) ?? null;
  const addBlock = (pageId: string, block: ReportBlock) => {
    updateReportBlocks(report.id, pageId, (blocks) => [...blocks, block], { label: "Add block" });
    setSelectedBlockId(block.id);
  };
  const updateSelectedBlock = (
    update: (block: ReportBlock) => ReportBlock,
    options?: EditOptions,
  ) => {
    if (selectedPage && selectedBlock)
      updateReportBlocks(
        report.id,
        selectedPage.id,
        (blocks) => blocks.map((block) => (block.id === selectedBlock.id ? update(block) : block)),
        options,
      );
  };
  const duplicateSelectedBlock = () => {
    if (!selectedPage || !selectedBlock) return;
    const copy = duplicateBlock(selectedBlock, selectedPage.blocks, pageMetrics(report.page));
    if (!copy) return;
    updateReportBlocks(report.id, selectedPage.id, (blocks) => [...blocks, copy], {
      label: "Duplicate block",
    });
    setSelectedBlockId(copy.id);
  };
  const removeSelectedBlock = () => {
    if (!selectedPage || !selectedBlock) return;
    updateReportBlocks(
      report.id,
      selectedPage.id,
      (blocks) => blocks.filter((block) => block.id !== selectedBlock.id),
      { label: "Delete block" },
    );
    setSelectedBlockId(null);
  };

  // Undo can remove the block that's selected.
  useEffect(() => {
    if (selectedBlockId && !selectedBlock) setSelectedBlockId(null);
  }, [selectedBlockId, selectedBlock]);

  // Cmd/Ctrl+Z undoes, with Shift (or Ctrl+Y) redoes. A text field keeps its own undo.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.altKey || !(event.metaKey || event.ctrlKey)) return;
      if (
        (event.target as HTMLElement | null)?.closest(
          'input, textarea, select, [contenteditable="true"]',
        )
      )
        return;
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) undoReport(report.id);
      else if ((key === "z" && event.shiftKey) || key === "y") redoReport(report.id);
      else return;
      event.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [report.id, undoReport, redoReport]);
  const widgets: WidgetsStatus =
    catalogueState.status === "ready"
      ? { status: "ready" }
      : catalogueState.status === "loading"
        ? { status: "loading" }
        : { status: "error", error: catalogueState.error };

  return (
    <div className="bg-surface-900 flex h-full w-full flex-col overflow-hidden">
      <header className="border-surface-700 flex min-h-14 shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b px-5 py-2">
        <div className="mr-auto min-w-0">
          <h1 className="text-surface-50 truncate text-[14px] font-semibold">{report.name}</h1>
          <p className="text-surface-400 mt-0.5 flex items-center gap-1.5 truncate text-[11px]">
            <LuChartBar size={12} className="shrink-0" />
            {pageSetupLabel(report.page)} · {pageCount} {pageCount === 1 ? "page" : "pages"}
          </p>
        </div>
        <div data-tour="report-view-controls" className="flex items-center gap-1">
          <ViewButton
            label={undoStep ? `Undo ${undoStep.label.toLowerCase()} (Ctrl/Cmd+Z)` : "Undo"}
            onClick={() => undoReport(report.id)}
            disabled={!undoStep}
          >
            <LuUndo2 size={14} />
          </ViewButton>
          <ViewButton
            label={redoStep ? `Redo ${redoStep.label.toLowerCase()} (Shift+Ctrl/Cmd+Z)` : "Redo"}
            onClick={() => redoReport(report.id)}
            disabled={!redoStep}
          >
            <LuRedo2 size={14} />
          </ViewButton>
          <span aria-hidden className="bg-surface-600 mx-1 h-4 w-px" />
          <ViewButton
            label="Zoom out"
            onClick={() => stepZoom(-1)}
            disabled={scale <= ZOOM_STEPS[0] + 0.001}
          >
            <LuZoomOut size={14} />
          </ViewButton>
          <span className="text-surface-300 w-10 text-center text-[11px] tabular-nums">
            {Math.round(scale * 100)}%
          </span>
          <ViewButton
            label="Zoom in"
            onClick={() => stepZoom(1)}
            disabled={scale >= ZOOM_STEPS[ZOOM_STEPS.length - 1] - 0.001}
          >
            <LuZoomIn size={14} />
          </ViewButton>
          <ViewButton
            label="Fit page to window"
            onClick={() => setZoom("fit")}
            active={zoom === "fit"}
          >
            <LuMaximize size={14} />
          </ViewButton>
          <ViewButton
            label="Show grid"
            onClick={() => setShowGrid((shown) => !shown)}
            active={showGrid}
          >
            <LuGrid3X3 size={14} />
          </ViewButton>
        </div>
        <button
          type="button"
          data-tour="report-export"
          onClick={() => setIsExporting(true)}
          disabled={isExporting || widgets.status !== "ready"}
          aria-busy={isExporting}
          title="Opens the print dialog: choose Save as PDF"
          className="border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700 focus-visible:border-accent-500 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none disabled:opacity-50"
        >
          {isExporting ? (
            <LuLoaderCircle size={13} className="animate-spin" />
          ) : (
            <LuFileDown size={13} />
          )}
          {isExporting ? "Preparing…" : "Export PDF"}
        </button>
        <div className="text-surface-400 flex items-center gap-1.5 text-[11px]">
          <LuCalendarClock size={13} />
          Created {new Date(report.createdAt).toLocaleDateString()}
        </div>
      </header>

      <ResultCatalogueContext.Provider
        value={catalogueState.status === "ready" ? catalogueState.catalogue : null}
      >
        <div className="flex min-h-0 flex-1">
          {/* The desk the paper lies on: a muted surface, so the white pages stand out. */}
          <div
            ref={deskRef}
            data-tour="report-desk"
            className="bg-surface-700 min-h-0 min-w-0 flex-1 overflow-auto"
          >
            <div
              className="mx-auto flex w-fit flex-col items-center gap-6"
              style={{ padding: DESK_PADDING }}
            >
              {report.pages.map((page, index) => (
                <div key={page.id} className="flex flex-col items-center gap-2">
                  <ReportPageView
                    page={page}
                    setup={report.page}
                    theme={report.theme}
                    reportName={report.name}
                    pageNumber={index + 1}
                    pageCount={pageCount}
                    scale={scale}
                    showGrid={showGrid}
                    widgets={widgets}
                    selectedBlockId={selectedBlockId}
                    onSelect={setSelectedBlockId}
                    onBlocksChange={(update, options) =>
                      updateReportBlocks(report.id, page.id, update, options)
                    }
                  />
                  <div className="text-surface-400 flex items-center gap-1.5 text-[11px]">
                    Page {index + 1} of {pageCount}
                    <button
                      type="button"
                      disabled={pageCount <= 1}
                      aria-label={`Delete page ${index + 1}`}
                      title={
                        pageCount <= 1 ? "A report needs at least one page" : "Delete this page"
                      }
                      onClick={() =>
                        page.blocks.length === 0
                          ? removeReportPage(report.id, page.id)
                          : setPageToRemove(page.id)
                      }
                      className="text-surface-400 hover:bg-surface-600 hover:text-danger-400 focus-visible:bg-surface-600 ml-1 flex h-5 items-center gap-1 rounded px-1.5 outline-none disabled:pointer-events-none disabled:opacity-40"
                    >
                      <LuTrash2 size={12} />
                      Delete page
                    </button>
                  </div>
                </div>
              ))}
              <button
                type="button"
                onClick={() => addReportPage(report.id)}
                className="border-surface-500 text-surface-300 hover:border-accent-500 hover:text-surface-50 flex h-8 items-center gap-1.5 rounded border border-dashed px-3 text-[12px] font-medium outline-none"
              >
                <LuPlus size={13} />
                Add page
              </button>
            </div>
          </div>
          <ReportSidePanel
            report={report}
            selectedBlock={selectedBlock}
            selectedPageId={selectedPage?.id ?? null}
            onAdd={addBlock}
            onUpdate={updateSelectedBlock}
            onDuplicate={duplicateSelectedBlock}
            onRemove={removeSelectedBlock}
            onThemeChange={(theme) => setReportTheme(report.id, theme)}
          />
        </div>
        {isExporting && <ReportPrintRoot report={report} widgets={widgets} onDone={finishExport} />}
      </ResultCatalogueContext.Provider>
      <ConfirmDialog
        open={pageToRemove !== null}
        onOpenChange={(open) => !open && setPageToRemove(null)}
        title="Delete Page"
        description="Delete this page and everything on it? Undo (Ctrl/⌘+Z) brings it back."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pageToRemove) removeReportPage(report.id, pageToRemove);
          setPageToRemove(null);
          setSelectedBlockId(null);
        }}
      />
    </div>
  );
}
