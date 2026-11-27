// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { BlockRect, PageSetup, ReportBlock, ReportPage } from "../data/reports";
import type { ReportTheme } from "../data/report-themes";
import { duplicateBlock } from "../lib/report-blocks";
import type { EditOptions } from "../lib/report-history";
import {
  blockBox,
  isFree,
  minBlockSize,
  moveRect,
  pageMetrics,
  resizeRect,
  type ResizeEdges,
} from "../lib/report-layout";
import { reportThemeStyle } from "../lib/report-theme";
import { ReportBlockView, type WidgetsStatus } from "./report-block-view";
import { ReportPageDecoration } from "./report-page-decoration";

// Eight grips: the corners and the edges.
const HANDLES: { edges: ResizeEdges; position: string; cursor: string }[] = [
  {
    edges: { top: true, left: true },
    position: "left-0 top-0 -translate-x-1/2 -translate-y-1/2",
    cursor: "nwse-resize",
  },
  {
    edges: { top: true },
    position: "left-1/2 top-0 -translate-x-1/2 -translate-y-1/2",
    cursor: "ns-resize",
  },
  {
    edges: { top: true, right: true },
    position: "right-0 top-0 translate-x-1/2 -translate-y-1/2",
    cursor: "nesw-resize",
  },
  {
    edges: { right: true },
    position: "right-0 top-1/2 translate-x-1/2 -translate-y-1/2",
    cursor: "ew-resize",
  },
  {
    edges: { bottom: true, right: true },
    position: "right-0 bottom-0 translate-x-1/2 translate-y-1/2",
    cursor: "nwse-resize",
  },
  {
    edges: { bottom: true },
    position: "left-1/2 bottom-0 -translate-x-1/2 translate-y-1/2",
    cursor: "ns-resize",
  },
  {
    edges: { bottom: true, left: true },
    position: "left-0 bottom-0 -translate-x-1/2 translate-y-1/2",
    cursor: "nesw-resize",
  },
  {
    edges: { left: true },
    position: "left-0 top-1/2 -translate-x-1/2 -translate-y-1/2",
    cursor: "ew-resize",
  },
];
const HANDLE_SIZE_PX = 9;

type Draft = { id: string; rect: BlockRect; isValid: boolean };

/**
 * One paper page at the given scale. The page is laid out at its real pixel
 * size and scaled as a whole, inside a box of the scaled size so the scroll
 * area around it is right. The page keeps its own light scheme, whatever the
 * app's theme is.
 *
 * Blocks are laid out on the grid: click to select, drag to move, drag a grip
 * to resize, arrow keys to nudge (Shift resizes), Delete to remove and Cmd/Ctrl+D
 * to duplicate. A block can't overlap another or leave the page; while it
 * would, it shows red and goes back where it was when let go.
 */
export function ReportPageView({
  page,
  setup,
  theme,
  reportName,
  pageNumber,
  pageCount,
  scale,
  showGrid,
  widgets,
  selectedBlockId,
  onSelect,
  onBlocksChange,
}: {
  page: ReportPage;
  setup: PageSetup;
  theme: ReportTheme;
  reportName: string;
  pageNumber: number;
  pageCount: number;
  scale: number;
  showGrid: boolean;
  widgets: WidgetsStatus;
  selectedBlockId: string | null;
  onSelect: (blockId: string | null) => void;
  onBlocksChange: (update: (blocks: ReportBlock[]) => ReportBlock[], options?: EditOptions) => void;
}) {
  const metrics = pageMetrics(setup);
  const [draft, setDraft] = useState<Draft | null>(null);
  const stopDrag = useRef<(() => void) | null>(null);
  useEffect(() => () => stopDrag.current?.(), []);

  const setRect = (id: string, rect: BlockRect, options?: EditOptions) =>
    onBlocksChange(
      (blocks) => blocks.map((block) => (block.id === id ? { ...block, rect } : block)),
      options,
    );

  // Moves or resizes `block` with the pointer, in whole cells.
  const startDrag = (block: ReportBlock, edges: ResizeEdges | null, event: ReactPointerEvent) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    onSelect(block.id);
    const startX = event.clientX;
    const startY = event.clientY;
    const min = minBlockSize(block.content);
    const rectAt = (clientX: number, clientY: number) => {
      const dCols = Math.round((clientX - startX) / (scale * metrics.columnWidth));
      const dRows = Math.round((clientY - startY) / (scale * metrics.rowHeight));
      return edges
        ? resizeRect(block.rect, edges, dCols, dRows, min, metrics)
        : moveRect(block.rect, dCols, dRows, metrics);
    };
    const onMove = (move: PointerEvent) => {
      const rect = rectAt(move.clientX, move.clientY);
      setDraft({ id: block.id, rect, isValid: isFree(rect, page.blocks, block.id) });
    };
    const end = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", end);
      stopDrag.current = null;
      setDraft(null);
    };
    const onUp = (up: PointerEvent) => {
      const rect = rectAt(up.clientX, up.clientY);
      const isChanged =
        rect.x !== block.rect.x ||
        rect.y !== block.rect.y ||
        rect.w !== block.rect.w ||
        rect.h !== block.rect.h;
      if (isChanged && isFree(rect, page.blocks, block.id))
        setRect(block.id, rect, { label: edges ? "Resize block" : "Move block" });
      end();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", end);
    stopDrag.current = end;
  };

  const handleKeyDown = (block: ReportBlock, event: KeyboardEvent) => {
    const arrow = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[
      event.key
    ];
    if (arrow) {
      event.preventDefault();
      const [dx, dy] = arrow;
      const rect = event.shiftKey
        ? resizeRect(
            block.rect,
            { right: true, bottom: true },
            dx,
            dy,
            minBlockSize(block.content),
            metrics,
          )
        : moveRect(block.rect, dx, dy, metrics);
      // A run of arrow presses is one undo step.
      if (isFree(rect, page.blocks, block.id))
        setRect(block.id, rect, {
          label: event.shiftKey ? "Resize block" : "Move block",
          mergeKey: `nudge:${block.id}:${event.shiftKey}`,
        });
    } else if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      onBlocksChange((blocks) => blocks.filter((item) => item.id !== block.id), {
        label: "Delete block",
      });
      onSelect(null);
    } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") {
      event.preventDefault();
      const copy = duplicateBlock(block, page.blocks, metrics);
      if (!copy) return;
      onBlocksChange((blocks) => [...blocks, copy], { label: "Duplicate block" });
      onSelect(copy.id);
    } else if (event.key === "Escape") {
      onSelect(null);
      (event.currentTarget as HTMLElement).blur();
    }
  };

  return (
    <div
      style={{ width: metrics.width * scale, height: metrics.height * scale }}
      className="shrink-0"
    >
      <div
        data-scheme={theme.scheme}
        data-report-page=""
        style={{
          ...reportThemeStyle(theme),
          width: metrics.width,
          height: metrics.height,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
        }}
        className="relative overflow-hidden shadow-lg shadow-black/30"
        // A press on the bare page clears the selection.
        onPointerDown={(event) => event.target === event.currentTarget && onSelect(null)}
      >
        <ReportPageDecoration
          theme={theme}
          width={metrics.width}
          height={metrics.height}
          reportName={reportName}
          pageNumber={pageNumber}
          pageCount={pageCount}
        />
        {showGrid && (
          // The margins, and the cells blocks snap to.
          <div
            aria-hidden
            className="border-accent-400/50 pointer-events-none absolute border border-dashed"
            style={{
              left: metrics.margin,
              top: metrics.margin,
              width: metrics.width - 2 * metrics.margin,
              height: metrics.rows * metrics.rowHeight,
              backgroundImage:
                "linear-gradient(to right, rgb(86 153 255 / 0.18) 1px, transparent 1px), linear-gradient(to bottom, rgb(86 153 255 / 0.12) 1px, transparent 1px)",
              backgroundSize: `${metrics.columnWidth}px ${metrics.rowHeight}px`,
            }}
          />
        )}
        {page.blocks.length === 0 && (
          <div className="text-surface-400 pointer-events-none absolute inset-0 flex items-center justify-center text-[13px]">
            This page is empty
          </div>
        )}
        {page.blocks.map((block) => {
          const isSelected = block.id === selectedBlockId;
          const isDragged = draft?.id === block.id;
          const rect = isDragged ? draft.rect : block.rect;
          const handleSize = HANDLE_SIZE_PX / scale;
          return (
            <div
              key={block.id}
              className="absolute"
              style={{
                ...blockBox(rect, metrics),
                zIndex: isDragged ? 20 : isSelected ? 10 : undefined,
              }}
            >
              {/* Pointer events go to the frame, so a chart or map never swallows a drag. */}
              <div className="pointer-events-none h-full w-full">
                <ReportBlockView block={block} widgets={widgets} theme={theme} flagOverflow />
              </div>
              <div
                role="button"
                tabIndex={0}
                aria-label={`${block.content.kind} block`}
                aria-pressed={isSelected}
                onPointerDown={(event) => {
                  event.currentTarget.focus();
                  startDrag(block, null, event);
                }}
                onKeyDown={(event) => handleKeyDown(block, event)}
                className={`absolute inset-0 ${isDragged ? "cursor-grabbing" : "cursor-grab"} ${
                  isDragged && !draft.isValid
                    ? "bg-danger-500/20 outline-danger-500 outline-2"
                    : isSelected
                      ? "outline-accent-500 outline-2"
                      : "hover:outline-accent-400/60 hover:outline"
                }`}
              />
              {isSelected &&
                HANDLES.map((handle) => (
                  <div
                    key={handle.position}
                    onPointerDown={(event) => startDrag(block, handle.edges, event)}
                    style={{ width: handleSize, height: handleSize, cursor: handle.cursor }}
                    className={`border-accent-500 absolute rounded-[1px] border bg-white ${handle.position}`}
                  />
                ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
