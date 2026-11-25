// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react";
import { Popover } from "@base-ui/react/popover";
import { LuArrowDown, LuArrowUp, LuFilter } from "react-icons/lu";
import { formatNumber } from "../../project/lib/record-format";
import { useLevelStore, type ColumnFilter } from "../level-store";
import { BINS, columnStatistics, filterKind, type TableColumn } from "./columns";

// A column's funnel: sort, filter by its type (a range, a checkbox list with
// counts, or "Contains…"), then statistics over the rows passing every
// filter. Esc or a click outside closes it.

const parseNumber = (text: string): number | null => {
  const value = Number(text.replace(/,/g, "").trim());
  return text.trim() === "" || !Number.isFinite(value) ? null : value;
};

const formatStat = (value: number) =>
  formatNumber(Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 1000) / 1000);

export function ColumnMenu<R>({
  column,
  rows,
  filteredRows,
}: {
  column: TableColumn<R>;
  /** Every row of the level: the filter's choices. */ rows: readonly R[];
  /** Rows passing every filter: the statistics. */ filteredRows: readonly R[];
}) {
  const filter = useLevelStore((s) => s.columnFilters[column.key]);
  const active = filter !== undefined;
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={`Filter ${column.header}`}
        title={active ? "Filtered" : "Filter"}
        onClick={(event) => event.stopPropagation()}
        className={`focus-visible:ring-accent-500 data-[popup-open]:bg-surface-700 flex h-5 w-5 shrink-0 items-center justify-center rounded outline-none focus-visible:ring-1 ${
          active ? "text-accent-400" : "text-surface-500 hover:text-surface-100"
        }`}
      >
        <LuFilter size={11} fill={active ? "currentColor" : "none"} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner
          className="z-50 outline-none"
          side="bottom"
          align="start"
          sideOffset={4}
          collisionPadding={8}
        >
          <Popover.Popup
            aria-label={`Sort and filter ${column.header}`}
            className="border-surface-600 bg-surface-800 text-surface-100 flex max-h-[min(36rem,var(--available-height))] w-72 flex-col gap-2 overflow-auto rounded-md border p-3 text-[12px] font-normal shadow-2xl shadow-black/50 outline-none"
          >
            <MenuBody column={column} rows={rows} filteredRows={filteredRows} filter={filter} />
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

const heading = "text-[10px] font-medium tracking-wide text-surface-400 uppercase";
const linkButton =
  "rounded px-1 text-[11px] text-accent-300 outline-none hover:underline focus-visible:ring-1 focus-visible:ring-accent-500 disabled:text-surface-500 disabled:no-underline";

function MenuBody<R>({
  column,
  rows,
  filteredRows,
  filter,
}: {
  column: TableColumn<R>;
  rows: readonly R[];
  filteredRows: readonly R[];
  filter: ColumnFilter | undefined;
}) {
  const sort = useLevelStore((s) => s.columnSort);
  const setSort = useLevelStore((s) => s.setColumnSort);
  const setFilter = useLevelStore((s) => s.setColumnFilter);
  const kind = useMemo(() => filterKind(column, rows), [column, rows]);
  const direction = sort?.column === column.key ? sort.direction : null;
  const sortButton = (value: "asc" | "desc") => (
    <button
      type="button"
      aria-pressed={direction === value}
      onClick={() => setSort(direction === value ? null : { column: column.key, direction: value })}
      className={`focus-visible:ring-accent-500 flex h-6 items-center gap-1 rounded border px-2 text-[11px] outline-none focus-visible:ring-1 ${
        direction === value
          ? "border-accent-500 bg-accent-600/20 text-accent-100"
          : "border-surface-600 text-surface-200 hover:border-surface-500"
      }`}
    >
      {value === "asc" ? <LuArrowUp size={11} /> : <LuArrowDown size={11} />}
      {value === "asc" ? "Ascending" : "Descending"}
    </button>
  );

  return (
    <>
      <div className={heading}>Sort</div>
      <div className="flex gap-1.5">
        {sortButton("asc")}
        {sortButton("desc")}
      </div>
      <div className={heading}>Filter</div>
      {kind.kind === "range" ? (
        <RangeFilter
          column={column}
          rows={rows}
          filter={filter}
          onChange={(next) => setFilter(column.key, next)}
        />
      ) : kind.kind === "values" ? (
        <ValuesFilter
          column={column}
          counts={kind.counts}
          filter={filter}
          onChange={(next) => setFilter(column.key, next)}
        />
      ) : (
        <input
          type="search"
          autoFocus
          placeholder="Contains…"
          aria-label={`Filter ${column.header}`}
          value={filter?.kind === "contains" ? filter.text : ""}
          onChange={(event) =>
            setFilter(
              column.key,
              event.target.value ? { kind: "contains", text: event.target.value } : null,
            )
          }
          className="border-surface-600 bg-surface-950 placeholder:text-surface-500 focus:border-accent-500 h-7 rounded border px-2 text-[12px] outline-none"
        />
      )}
      <div className="flex justify-end">
        <button
          type="button"
          disabled={!filter}
          onClick={() => setFilter(column.key, null)}
          className={linkButton}
        >
          Clear filter
        </button>
      </div>
      <div className="border-surface-600/60 border-t" />
      <Statistics column={column} rows={filteredRows} />
    </>
  );
}

function RangeFilter<R>({
  column,
  rows,
  filter,
  onChange,
}: {
  column: TableColumn<R>;
  rows: readonly R[];
  filter: ColumnFilter | undefined;
  onChange: (filter: ColumnFilter | null) => void;
}) {
  const range = filter?.kind === "range" ? filter : null;
  // What's typed stays as typed (a half-written "1."), the filter takes the number.
  const [min, setMin] = useState(range?.min?.toString() ?? "");
  const [max, setMax] = useState(range?.max?.toString() ?? "");
  const bounds = useMemo(() => {
    const numbers = rows
      .map((row) => column.value(row))
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    return numbers.length ? { lo: Math.min(...numbers), hi: Math.max(...numbers) } : null;
  }, [column, rows]);
  const update = (nextMin: string, nextMax: string) => {
    const lo = parseNumber(nextMin);
    const hi = parseNumber(nextMax);
    onChange(lo === null && hi === null ? null : { kind: "range", min: lo, max: hi });
  };
  const input =
    "h-7 min-w-0 flex-1 rounded border border-surface-600 bg-surface-950 px-2 text-[12px] tabular-nums outline-none placeholder:text-surface-500 focus:border-accent-500";
  return (
    <>
      <div className="flex items-center gap-1.5">
        <input
          inputMode="decimal"
          placeholder="Min"
          aria-label="Minimum"
          value={min}
          onChange={(event) => {
            setMin(event.target.value);
            update(event.target.value, max);
          }}
          className={input}
        />
        <span className="text-surface-400">–</span>
        <input
          inputMode="decimal"
          placeholder="Max"
          aria-label="Maximum"
          value={max}
          onChange={(event) => {
            setMax(event.target.value);
            update(min, event.target.value);
          }}
          className={input}
        />
      </div>
      <div className="text-surface-400 text-[11px]">
        {bounds
          ? `Values range from ${formatStat(bounds.lo)} to ${formatStat(bounds.hi)}`
          : "No values"}
      </div>
    </>
  );
}

function ValuesFilter<R>({
  column,
  counts,
  filter,
  onChange,
}: {
  column: TableColumn<R>;
  counts: [string, number][];
  filter: ColumnFilter | undefined;
  onChange: (filter: ColumnFilter | null) => void;
}) {
  const all = counts.map(([value]) => value);
  // No filter is every value ticked.
  const selected = filter?.kind === "values" ? new Set(filter.values) : new Set(all);
  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange(all.every((item) => next.has(item)) ? null : { kind: "values", values: [...next] });
  };
  return (
    <>
      <div className="flex gap-2">
        <button type="button" onClick={() => onChange(null)} className={linkButton}>
          Select all
        </button>
        <button
          type="button"
          onClick={() => onChange({ kind: "values", values: [] })}
          className={linkButton}
        >
          Select none
        </button>
      </div>
      <ul
        aria-label={`${column.header} values`}
        className="border-surface-700 max-h-56 overflow-auto rounded border py-0.5"
      >
        {counts.map(([value, count]) => (
          <li key={value}>
            <label className="hover:bg-surface-700/60 flex cursor-pointer items-center gap-2 px-2 py-0.5">
              <input
                type="checkbox"
                checked={selected.has(value)}
                onChange={() => toggle(value)}
                className="accent-accent-600"
              />
              <span className="min-w-0 flex-1 truncate" title={value}>
                {value === "" ? (
                  <span className="text-surface-400">(empty)</span>
                ) : (
                  (column.label?.(value) ?? value)
                )}
              </span>
              <span className="text-surface-400 shrink-0 tabular-nums">{formatNumber(count)}</span>
            </label>
          </li>
        ))}
      </ul>
    </>
  );
}

function StatLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-surface-400">{label}</span>
      <span className="truncate tabular-nums" title={value}>
        {value}
      </span>
    </div>
  );
}

function Statistics<R>({ column, rows }: { column: TableColumn<R>; rows: readonly R[] }) {
  const stats = useMemo(() => columnStatistics(column, rows), [column, rows]);
  return (
    <>
      <div className={heading}>
        Statistics · {formatNumber(stats.n)} {stats.n === 1 ? "row" : "rows"}
      </div>
      {stats.n === 0 ? (
        <div className="text-surface-400">No rows</div>
      ) : stats.kind === "empty" ? (
        <div className="text-surface-400">All values missing</div>
      ) : stats.kind === "number" ? (
        <>
          <Histogram bins={stats.bins} min={stats.min} max={stats.max} />
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px]">
            <StatLine label="mean" value={formatStat(stats.mean)} />
            <StatLine label="median" value={formatStat(stats.median)} />
            <StatLine label="p25" value={formatStat(stats.p25)} />
            <StatLine label="p75" value={formatStat(stats.p75)} />
            <StatLine label="min" value={formatStat(stats.min)} />
            <StatLine label="max" value={formatStat(stats.max)} />
            <StatLine label="unique" value={formatNumber(stats.unique)} />
            <StatLine label="missing" value={formatNumber(stats.missing)} />
          </div>
        </>
      ) : (
        <div className="flex flex-col gap-0.5 text-[11px]">
          <StatLine label="unique" value={formatNumber(stats.unique)} />
          {stats.top.length === 0 ? (
            <div className="text-surface-400">All values distinct</div>
          ) : (
            stats.top.map(([value, count]) => (
              <div key={value} className="flex items-baseline justify-between gap-2">
                <span className="truncate" title={value}>
                  {value === "" ? "(empty)" : (column.label?.(value) ?? value)}
                </span>
                <span className="text-surface-400 shrink-0 tabular-nums">
                  {formatNumber(count)}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </>
  );
}

const WIDTH = 240;
const HEIGHT = 40;

function Histogram({ bins, min, max }: { bins: number[]; min: number; max: number }) {
  const largest = Math.max(...bins);
  const width = WIDTH / BINS;
  const edge = (index: number) => min + ((max - min) * index) / BINS;
  return (
    <div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Distribution"
        className="text-accent-500 h-10 w-full"
      >
        {bins.map((count, index) => {
          if (count === 0) return null;
          const height = Math.max(1.5, (count / largest) * HEIGHT);
          return (
            <rect
              key={index}
              x={index * width + 0.5}
              y={HEIGHT - height}
              width={width - 1}
              height={height}
              rx={1}
              fill="currentColor"
            >
              <title>
                {formatStat(edge(index))} – {formatStat(edge(index + 1))}: {formatNumber(count)}
              </title>
            </rect>
          );
        })}
      </svg>
      <div className="text-surface-400 flex justify-between text-[10px] tabular-nums">
        <span>{formatStat(min)}</span>
        <span>{formatStat(max)}</span>
      </div>
    </div>
  );
}
