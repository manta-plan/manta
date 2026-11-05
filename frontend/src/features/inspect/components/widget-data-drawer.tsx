import { useMemo, useState, type PointerEvent } from "react";
import { createPortal } from "react-dom";
import { Tooltip } from "@base-ui/react/tooltip";
import { LuArrowDown, LuArrowUp, LuDownload, LuTable, LuX } from "react-icons/lu";
import { useWidgetDataDrawer } from "../../project/lib/widget-set-context";
import { WidgetTooltipPopup } from "./widget-icon-button";
import { widgetDataCsv, type WidgetData, type WidgetDataCell } from "../../project/lib/widget-data";

export const DATA_DRAWER_MIN_HEIGHT = 160;
export const DATA_DRAWER_DEFAULT_HEIGHT = 320;

// The inspection page's own bottom drawer, spanning the window like the
// Model tab's. It's an empty shell: the widget
// it shows renders its table into `onBodyRef`, so the table follows the
// result and filters as they change.
export function WidgetDataDrawer({
  isOpen,
  height,
  onHeightChange,
  onBodyRef,
}: {
  isOpen: boolean;
  height: number;
  onHeightChange: (height: number) => void;
  onBodyRef: (element: HTMLDivElement | null) => void;
}) {
  const resize = (event: PointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    onHeightChange(
      Math.max(
        DATA_DRAWER_MIN_HEIGHT,
        Math.min(window.innerHeight - event.clientY, window.innerHeight * 0.92),
      ),
    );
  };

  return createPortal(
    <div
      aria-hidden={!isOpen}
      inert={!isOpen}
      style={{ height }}
      className={`border-surface-600 bg-surface-800 fixed inset-x-0 bottom-0 z-30 flex flex-col rounded-t-lg border-t shadow-2xl shadow-black/50 transition-transform duration-200 ease-out ${isOpen ? "translate-y-0" : "pointer-events-none translate-y-full"}`}
    >
      <div
        role="separator"
        aria-label="Resize data drawer"
        aria-orientation="horizontal"
        onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
        onPointerMove={resize}
        className="flex h-3 shrink-0 cursor-row-resize touch-none items-center justify-center"
      >
        <div className="bg-surface-600 hover:bg-accent-500 h-1 w-10 rounded-full transition-colors" />
      </div>
      <div ref={onBodyRef} className="flex min-h-0 flex-1 flex-col" />
    </div>,
    document.body,
  );
}

type SortState = { column: number; direction: "asc" | "desc" } | null;

function compareCells(a: WidgetDataCell, b: WidgetDataCell) {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

function formatCell(cell: WidgetDataCell) {
  if (cell === null) return "—";
  if (typeof cell === "number")
    return cell.toLocaleString(undefined, {
      maximumFractionDigits: Math.abs(cell) < 1 && cell !== 0 ? 4 : 2,
    });
  return cell;
}

function fileName(title: string) {
  return `${title
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, "-")
    .replaceAll(/^-|-$/g, "")}.csv`;
}

function DataTable({
  title,
  data,
  onClose,
}: {
  title: string;
  data: WidgetData;
  onClose: () => void;
}) {
  const [sort, setSort] = useState<SortState>(null);
  const rows = useMemo(() => {
    if (!sort) return data.rows;
    const sorted = [...data.rows].sort((a, b) => compareCells(a[sort.column], b[sort.column]));
    return sort.direction === "asc" ? sorted : sorted.reverse();
  }, [data, sort]);

  // Ascending, then descending, then back to the widget's own order.
  const cycleSort = (column: number) =>
    setSort((current) =>
      current?.column !== column
        ? { column, direction: "asc" }
        : current.direction === "asc"
          ? { column, direction: "desc" }
          : null,
    );

  const download = () => {
    const url = URL.createObjectURL(
      new Blob([widgetDataCsv({ columns: data.columns, rows })], {
        type: "text/csv;charset=utf-8",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName(title);
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="border-surface-600 flex h-8 shrink-0 items-center justify-between gap-3 border-b px-3">
        <div className="text-surface-200 flex min-w-0 items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          <LuTable size={12} className="shrink-0" />
          <span className="truncate" title={title}>
            {title}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-surface-400 text-[11px]">
            {data.rows.length.toLocaleString()} rows
          </span>
          <button
            type="button"
            onClick={download}
            className="text-surface-300 hover:text-surface-50 flex items-center gap-1 text-[11px] outline-none"
          >
            <LuDownload size={12} />
            CSV
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close data"
            className="text-surface-400 hover:text-surface-100 outline-none"
          >
            <LuX size={14} />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto overscroll-contain text-[12px]">
        {data.rows.length === 0 ? (
          <div className="text-surface-400 flex h-full items-center justify-center">
            No data for the current filters.
          </div>
        ) : (
          <table className="w-full border-collapse">
            <thead className="bg-surface-800 text-surface-400 sticky top-0 z-10 text-left">
              <tr>
                {data.columns.map((column, index) => (
                  <th
                    key={column}
                    aria-sort={
                      sort?.column === index
                        ? sort.direction === "asc"
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                    className={`border-surface-600 border-b p-0 font-medium whitespace-nowrap ${index === 0 ? "bg-surface-800 sticky left-0" : ""}`}
                  >
                    <button
                      type="button"
                      onClick={() => cycleSort(index)}
                      className={`hover:text-surface-100 flex w-full items-center gap-1 px-3 py-1.5 outline-none ${index === 0 ? "" : "justify-end"} ${sort?.column === index ? "text-surface-100" : ""}`}
                    >
                      {column}
                      {sort?.column === index &&
                        (sort.direction === "asc" ? (
                          <LuArrowUp size={11} />
                        ) : (
                          <LuArrowDown size={11} />
                        ))}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="text-surface-200 hover:bg-surface-700/40">
                  {row.map((cell, columnIndex) => (
                    <td
                      key={columnIndex}
                      className={`border-surface-700/60 border-b px-3 py-1 whitespace-nowrap ${columnIndex === 0 ? "bg-surface-800 text-surface-100 sticky left-0 font-mono" : "text-right tabular-nums"}`}
                    >
                      {formatCell(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

// The widget's "View data" button. While its widget is the one shown, it
// also renders the table into the drawer.
export function WidgetDataButton({ title, data }: { title: string; data: WidgetData }) {
  const drawer = useWidgetDataDrawer();
  if (!drawer) return null;

  return (
    <>
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <button
              type="button"
              onClick={drawer.toggle}
              aria-pressed={drawer.isOpen}
              aria-label={`View data for ${title}`}
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none ${drawer.isOpen ? "bg-accent-600 text-white" : "text-surface-400 hover:bg-surface-700 hover:text-surface-50"}`}
            />
          }
        >
          <LuTable size={14} />
        </Tooltip.Trigger>
        <WidgetTooltipPopup label={drawer.isOpen ? "Hide data" : "View data"} />
      </Tooltip.Root>
      {drawer.isOpen &&
        drawer.target &&
        createPortal(<DataTable title={title} data={data} onClose={drawer.close} />, drawer.target)}
    </>
  );
}
