import { useMemo, useRef, type KeyboardEvent, type ReactNode } from "react";
import { LuArrowDown, LuArrowUp, LuArrowUpDown, LuChartLine } from "react-icons/lu";
import { formatNumber } from "../../project/lib/record-format";
import { useLevelStore } from "../level-store";
import { ColumnMenu } from "./column-menu";
import { ColumnPicker } from "./column-picker";
import { useHiddenColumns } from "./use-hidden-columns";
import { columnSeries, filterAndSort, type TableColumn } from "./columns";
import { TableBar } from "./table-bar";
import { ROW_HEIGHT, useRowWindow } from "./use-row-window";

// The members table: the header bar, a sticky header whose columns sort
// (↕ ↑ ↓, one at a time) and filter (the funnel), virtualised rows (only
// those in view render), and the "n of m" footer.

const MIN_CHARS = 6;
const MAX_CHARS = 36;
const SAMPLE = 2000;

/** A column's width in characters: its header or its longest value, within limits; columns don't jump as rows scroll by. */
function columnWidth<R>(column: TableColumn<R>, rows: readonly R[]) {
  let longest = column.header.length + 4;
  for (const row of rows.slice(0, SAMPLE)) {
    const value = column.value(row);
    const text =
      value === null
        ? ""
        : typeof value === "number"
          ? formatNumber(Math.round(value * 10) / 10)
          : (column.label?.(value) ?? value);
    longest = Math.max(longest, text.length + (column.kind === "series" ? 10 : 2));
  }
  return Math.max(MIN_CHARS, Math.min(column.maxChars ?? MAX_CHARS, longest));
}

export function DataTable<R>({
  title,
  noun,
  columns,
  rows,
  rowKey,
  onOpenRow,
  openLabel,
  isRefreshing = false,
  status,
}: {
  title: string;
  /** "entities" or "locations", for the footer. */
  noun: string;
  columns: TableColumn<R>[];
  rows: readonly R[];
  rowKey: (row: R) => string;
  onOpenRow?: (row: R) => void;
  openLabel?: (row: R) => string;
  isRefreshing?: boolean;
  /** A loading or error message in place of the rows. */
  status?: ReactNode;
}) {
  const filters = useLevelStore((s) => s.columnFilters);
  const sort = useLevelStore((s) => s.columnSort);
  const { hidden, setHidden } = useHiddenColumns();
  const headers = useMemo(() => columns.map((column) => column.header), [columns]);
  const visible = useMemo(() => {
    const shown = columns.filter((column) => !hidden.has(column.header));
    return shown.length > 0 ? shown : columns;
  }, [columns, hidden]);

  const shownRows = useMemo(
    () => filterAndSort(rows, columns, filters, sort),
    [rows, columns, filters, sort],
  );
  const widths = useMemo(
    () => new Map(columns.map((column) => [column.key, columnWidth(column, rows)])),
    [columns, rows],
  );
  const scroller = useRef<HTMLDivElement>(null);
  const { start, end } = useRowWindow(scroller, shownRows.length);
  const filterCount = columns.filter((column) => filters[column.key]).length;

  const footer =
    filterCount > 0 || shownRows.length !== rows.length
      ? `${formatNumber(shownRows.length)} of ${formatNumber(rows.length)} ${noun}`
      : `${formatNumber(rows.length)} ${noun}`;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TableBar
        title={title}
        picker={<ColumnPicker headers={headers} hidden={hidden} onChange={setHidden} />}
        filterCount={filterCount}
      />
      <div
        ref={scroller}
        className={`relative min-h-0 flex-1 overflow-auto text-[12px] ${isRefreshing ? "opacity-70" : ""}`}
      >
        <table className="min-w-full border-separate border-spacing-0">
          <thead className="bg-surface-900 text-surface-400 sticky top-0 z-10">
            <tr>
              {visible.map((column) => (
                <HeaderCell
                  key={column.key}
                  column={column}
                  width={widths.get(column.key) ?? MIN_CHARS}
                  rows={rows}
                  filteredRows={shownRows}
                />
              ))}
            </tr>
          </thead>
          {status === undefined && (
            <tbody>
              {start > 0 && (
                <tr aria-hidden style={{ height: start * ROW_HEIGHT }}>
                  <td colSpan={visible.length} />
                </tr>
              )}
              {shownRows.slice(start, end).map((row) => (
                <Row
                  key={rowKey(row)}
                  row={row}
                  columns={visible}
                  onOpen={onOpenRow}
                  label={openLabel?.(row)}
                />
              ))}
              {end < shownRows.length && (
                <tr aria-hidden style={{ height: (shownRows.length - end) * ROW_HEIGHT }}>
                  <td colSpan={visible.length} />
                </tr>
              )}
            </tbody>
          )}
        </table>
        {status !== undefined ? (
          <div className="text-surface-400 px-3 py-6 text-center text-[12px]">{status}</div>
        ) : (
          shownRows.length === 0 && (
            <div className="text-surface-400 px-3 py-6 text-center text-[12px]">
              {rows.length === 0 ? `No ${noun} here.` : `No ${noun} pass the column filters.`}
            </div>
          )
        )}
      </div>
      <div className="border-surface-700 text-surface-400 flex h-7 shrink-0 items-center border-t px-3 text-[11px] tabular-nums">
        {status === undefined ? footer : ""}
      </div>
    </div>
  );
}

function Row<R>({
  row,
  columns,
  onOpen,
  label,
}: {
  row: R;
  columns: TableColumn<R>[];
  onOpen?: (row: R) => void;
  label?: string;
}) {
  const open = onOpen ? () => onOpen(row) : undefined;
  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === "Enter" && event.target === event.currentTarget && open) {
      event.preventDefault();
      open();
    }
  };
  return (
    <tr
      tabIndex={open ? 0 : undefined}
      aria-label={label}
      onClick={open}
      onKeyDown={onKeyDown}
      style={{ height: ROW_HEIGHT }}
      className={`group text-surface-200 hover:bg-surface-800 focus-visible:bg-surface-800 outline-none focus-visible:shadow-[inset_2px_0_0_var(--color-accent-500)] ${open ? "cursor-pointer" : ""}`}
    >
      {columns.map((column) => (
        <td
          key={column.key}
          title={column.cellTitle?.(row)}
          className={`border-surface-800 overflow-hidden border-b px-3 py-0 whitespace-nowrap ${column.kind === "number" ? "text-right tabular-nums" : ""} ${column.cellClass?.(row) ?? ""}`}
          style={{ maxWidth: `${(column.maxChars ?? MAX_CHARS) + 4}ch` }}
        >
          <div
            className="flex min-w-0 items-center truncate"
            style={{ justifyContent: column.kind === "number" ? "flex-end" : undefined }}
          >
            {column.render(row)}
          </div>
        </td>
      ))}
    </tr>
  );
}

function HeaderCell<R>({
  column,
  width,
  rows,
  filteredRows,
}: {
  column: TableColumn<R>;
  width: number;
  rows: readonly R[];
  filteredRows: readonly R[];
}) {
  const sort = useLevelStore((s) => s.columnSort);
  const setSort = useLevelStore((s) => s.setColumnSort);
  const direction = sort?.column === column.key ? sort.direction : null;
  const cycle = () =>
    setSort(
      direction === null
        ? { column: column.key, direction: "asc" }
        : direction === "asc"
          ? { column: column.key, direction: "desc" }
          : null,
    );
  const SortIcon =
    direction === "asc" ? LuArrowUp : direction === "desc" ? LuArrowDown : LuArrowUpDown;
  return (
    <th
      scope="col"
      aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}
      title={column.description}
      style={{ minWidth: `${width}ch` }}
      className="border-surface-700 border-b px-3 py-1.5 text-left font-medium whitespace-nowrap"
    >
      <span className={`flex items-center gap-1 ${column.kind === "number" ? "justify-end" : ""}`}>
        <span className="truncate">{column.header}</span>
        {column.series && <ChartAll column={column} rows={filteredRows} />}
        <button
          type="button"
          onClick={cycle}
          aria-label={`Sort by ${column.header}`}
          title={
            direction === "asc"
              ? "Sorted ascending"
              : direction === "desc"
                ? "Sorted descending"
                : "Sort"
          }
          className={`focus-visible:ring-accent-500 flex h-5 w-5 shrink-0 items-center justify-center rounded outline-none focus-visible:ring-1 ${direction ? "text-accent-400" : "text-surface-500 hover:text-surface-100"}`}
        >
          <SortIcon size={11} />
        </button>
        <ColumnMenu column={column} rows={rows} filteredRows={filteredRows} />
      </span>
    </th>
  );
}

/** "Chart all" on a series column with more than one series of one attribute in view; "Unchart all" while it's charted. */
function ChartAll<R>({ column, rows }: { column: TableColumn<R>; rows: readonly R[] }) {
  const { count, attribute } = useMemo(() => columnSeries(column, rows), [column, rows]);
  const isOn = useLevelStore(
    (s) =>
      s.chartMode === "attributes" &&
      s.chartAttribute === attribute &&
      s.chartAggregation === "all",
  );
  const setMode = useLevelStore((s) => s.setChartMode);
  const setAttribute = useLevelStore((s) => s.setChartAttribute);
  const setAggregation = useLevelStore((s) => s.setChartAggregation);
  if (count < 2 || attribute === null) return null;
  const toggle = () => {
    if (isOn) {
      setAggregation(null);
      return;
    }
    setMode("attributes");
    setAttribute(attribute);
    setAggregation("all");
  };
  return (
    <button
      type="button"
      aria-pressed={isOn}
      onClick={toggle}
      title={
        isOn
          ? "Set the chart back to its default aggregation"
          : `Chart every series of ${attribute}: the chart shows this attribute with Aggregation “All”`
      }
      className={`focus-visible:ring-accent-500 flex h-5 shrink-0 items-center gap-1 rounded border px-1.5 text-[10.5px] font-normal outline-none focus-visible:ring-1 ${
        isOn
          ? "border-accent-500 bg-accent-600/25 text-accent-100"
          : "border-surface-600 text-accent-300 hover:border-accent-500"
      }`}
    >
      <LuChartLine size={10} />
      {isOn ? "Unchart all" : "Chart all"}
    </button>
  );
}
