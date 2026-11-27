// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import type { ColumnFilter, ColumnSort, PickedSeries } from "../level-store";

// A table column: how its cells read (for sorting, filtering and statistics)
// and how they show. Every level's table is a list of these over its rows.

export type CellValue = number | string | null;

export interface TableColumn<R> {
  /** Stable key: the store's filters and sort use it ("carrier" for the Carrier column, which the graph may filter). */
  key: string;
  /** What the header says; hidden columns are remembered by it. */
  header: string;
  /** The header's tooltip. */
  description?: string;
  /** 'number' filters by range; 'text' by values or a substring; 'series' by values (a series, a constant, or "—"). */
  kind: "number" | "text" | "series";
  /** The cell's value for sorting, filtering and statistics. */
  value: (row: R) => CellValue;
  render: (row: R) => ReactNode;
  /** How a value reads in the filter's checkbox list (a carrier's nice name). */
  label?: (value: string) => string;
  /** Extra classes for a cell (a default in grey italic, a changed value). */
  cellClass?: (row: R) => string | undefined;
  cellTitle?: (row: R) => string | undefined;
  /** A series column: the row's series, for "Chart all". */
  series?: (row: R) => PickedSeries | null;
  /** Text only fits so wide: the cell truncates past this many characters. */
  maxChars?: number;
}

/** The value a series column filters by for a row with a series. */
export const SERIES_VALUE = "time series";

export const isEmpty = (value: CellValue) => value === null || value === "";

/** Whether a value passes a column's filter. */
export function passes(filter: ColumnFilter | undefined, value: CellValue): boolean {
  if (!filter) return true;
  switch (filter.kind) {
    case "range": {
      if (filter.min === null && filter.max === null) return true;
      if (typeof value !== "number") return false;
      return (
        (filter.min === null || value >= filter.min) && (filter.max === null || value <= filter.max)
      );
    }
    case "values":
      return filter.values.includes(value === null ? "" : String(value));
    case "contains":
      return (
        !filter.text ||
        (value !== null && String(value).toLowerCase().includes(filter.text.toLowerCase()))
      );
  }
}

/** Rows passing every filter (filters of hidden columns too), then sorted by one column, empties last. */
export function filterAndSort<R>(
  rows: readonly R[],
  columns: readonly TableColumn<R>[],
  filters: Record<string, ColumnFilter>,
  sort: ColumnSort | null,
): R[] {
  const active = columns.filter((column) => filters[column.key]);
  const kept =
    active.length === 0
      ? [...rows]
      : rows.filter((row) =>
          active.every((column) => passes(filters[column.key], column.value(row))),
        );
  const column = sort ? columns.find((item) => item.key === sort.column) : undefined;
  if (!sort || !column) return kept;
  const direction = sort.direction === "asc" ? 1 : -1;
  const keyed = kept.map((row) => ({ row, value: column.value(row) }));
  keyed.sort((a, b) => {
    const x = a.value;
    const y = b.value;
    if (isEmpty(x) || isEmpty(y)) return isEmpty(x) && isEmpty(y) ? 0 : isEmpty(x) ? 1 : -1;
    if (typeof x === "number" && typeof y === "number") return (x - y) * direction;
    return String(x).localeCompare(String(y), undefined, { numeric: true }) * direction;
  });
  return keyed.map((item) => item.row);
}

/** Up to this many distinct text values, a column filters with a checkbox list; past it, with "Contains…". */
export const MAX_LISTED_VALUES = 40;

/** How a column filters: by range, a checkbox list, or a substring. */
export function filterKind<R>(
  column: TableColumn<R>,
  rows: readonly R[],
): { kind: "range" } | { kind: "values"; counts: [string, number][] } | { kind: "contains" } {
  if (column.kind === "number") return { kind: "range" };
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = column.value(row);
    const text = value === null ? "" : String(value);
    counts.set(text, (counts.get(text) ?? 0) + 1);
    if (column.kind === "text" && counts.size > MAX_LISTED_VALUES) return { kind: "contains" };
  }
  const sorted = [...counts].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0], undefined, { numeric: true }),
  );
  return { kind: "values", counts: sorted };
}

export interface NumberStatistics {
  kind: "number";
  n: number;
  bins: number[];
  min: number;
  max: number;
  mean: number;
  median: number;
  p25: number;
  p75: number;
  unique: number;
  missing: number;
}

export interface TextStatistics {
  kind: "text";
  n: number;
  unique: number;
  top: [string, number][];
}

export const BINS = 24;

/** A column's statistics over rows (those passing every filter). Null when there are none, or no number at all. */
export function columnStatistics<R>(
  column: TableColumn<R>,
  rows: readonly R[],
): NumberStatistics | TextStatistics | { kind: "empty"; n: number } {
  const values = rows.map((row) => column.value(row));
  const n = values.length;
  if (column.kind === "number") {
    const numbers = values
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
      .sort((a, b) => a - b);
    if (numbers.length === 0) return { kind: "empty", n };
    const quantile = (p: number) => {
      const at = (numbers.length - 1) * p;
      const floor = Math.floor(at);
      return (
        numbers[floor] +
        (numbers[Math.min(floor + 1, numbers.length - 1)] - numbers[floor]) * (at - floor)
      );
    };
    const min = numbers[0];
    const max = numbers[numbers.length - 1];
    const bins = new Array<number>(BINS).fill(0);
    for (const value of numbers)
      bins[max > min ? Math.min(BINS - 1, Math.floor(((value - min) / (max - min)) * BINS)) : 0] +=
        1;
    return {
      kind: "number",
      n,
      bins,
      min,
      max,
      mean: numbers.reduce((sum, value) => sum + value, 0) / numbers.length,
      median: quantile(0.5),
      p25: quantile(0.25),
      p75: quantile(0.75),
      unique: new Set(numbers).size,
      missing: n - numbers.length,
    };
  }
  const counts = new Map<string, number>();
  for (const value of values) {
    const text = value === null ? "" : String(value);
    counts.set(text, (counts.get(text) ?? 0) + 1);
  }
  return {
    kind: "text",
    n,
    unique: counts.size,
    top: counts.size < n ? [...counts].sort((a, b) => b[1] - a[1]).slice(0, 3) : [],
  };
}

/** The series a column has among rows, and the one attribute they share ("Generator · p_max_pu"), if they share one. */
export function columnSeries<R>(
  column: TableColumn<R>,
  rows: readonly R[],
): { count: number; attribute: string | null } {
  if (!column.series) return { count: 0, attribute: null };
  const attributes = new Set<string>();
  let count = 0;
  for (const row of rows) {
    const series = column.series(row);
    if (!series) continue;
    count += 1;
    attributes.add(`${series.ctype} · ${series.attribute}`);
  }
  return { count, attribute: attributes.size === 1 ? [...attributes][0] : null };
}
