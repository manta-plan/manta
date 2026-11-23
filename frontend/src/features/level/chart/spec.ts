// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

// What the chart drawer draws, whatever it charts: a time series over the
// window (lines, stacked areas, or a distribution band), a duration curve,
// or bars. Statistics and attributes both end in one of these; SpecChart
// paints it.

/** One series of values, aligned to the chart's x values. */
export interface SpecSeries {
  name: string;
  color: string;
  values: (number | null)[];
}

/** The quantiles of many series at each x: drawn as a median line in a P25–P75 and a min–max band. */
export interface Distribution {
  /** How many series it sums up. */
  count: number;
  min: number[];
  p25: number[];
  median: number[];
  p75: number[];
  max: number[];
}

export type ChartSpec =
  | {
      kind: "time";
      /** The y axis' unit, e.g. "GW". */
      unit: string;
      /** Epoch milliseconds, one per snapshot of the window. */
      times: number[];
      series: SpecSeries[];
      stacked?: boolean;
      distribution?: Distribution;
    }
  | {
      /** Values sorted high to low against hours (or a rank). */
      kind: "duration";
      unit: string;
      xName: string;
      /** x per position: cumulative hours, or 1…n. */
      x: number[];
      series: SpecSeries[];
    }
  | {
      kind: "bar";
      unit: string;
      categories: string[];
      series: SpecSeries[];
      stacked?: boolean;
      /** One colour per bar (a single series coloured by category, e.g. carriers). */
      barColors?: string[];
    };

/** The 12 colours picked series take, in pick order. */
export const PALETTE = [
  "#5699ff",
  "#f59f3a",
  "#3fbf9f",
  "#e05bb0",
  "#c8c84a",
  "#9b86ff",
  "#4fc3e8",
  "#e06c5b",
  "#7fd36b",
  "#d48cff",
  "#f2c94c",
  "#5fa8a0",
];

/** More series than this in one plot draw as a distribution (an open question; 12 for now). */
export const LINE_THRESHOLD = 12;

export const NEUTRAL = "#94a3b8";
export const ACCENT = "#5699ff";

/** Whether a unit is per unit (a share of capacity): averaged capacity-weighted, never summed. */
export function isPerUnit(unit: string | null | undefined): boolean {
  return unit === "per unit" || unit === "p.u.";
}

/** Whether a unit is a price or a rate (currency per MWh and the like): never summed. */
export function isRate(unit: string | null | undefined): boolean {
  return !!unit && (unit.includes("/") || unit.includes("currency"));
}

/** A sum's unit: MW and MWh read better in GW and GWh. */
export function sumUnit(unit: string | null | undefined): { unit: string; scale: number } {
  if (unit === "MW") return { unit: "GW", scale: 1e-3 };
  if (unit === "MWh") return { unit: "GWh", scale: 1e-3 };
  return { unit: unit ?? "", scale: 1 };
}

/** The quantiles at each position of many equally long series (nulls skipped). */
export function distributionOf(series: (number | null)[][]): Distribution {
  const length = series[0]?.length ?? 0;
  const out: Distribution = {
    count: series.length,
    min: [],
    p25: [],
    median: [],
    p75: [],
    max: [],
  };
  const quantile = (sorted: number[], q: number) => {
    const at = (sorted.length - 1) * q;
    const low = Math.floor(at);
    return sorted[low] + (sorted[Math.min(sorted.length - 1, low + 1)] - sorted[low]) * (at - low);
  };
  for (let index = 0; index < length; index += 1) {
    const values = series
      .map((values) => values[index])
      .filter((value): value is number => value !== null && Number.isFinite(value));
    values.sort((a, b) => a - b);
    const has = values.length > 0;
    out.min.push(has ? values[0] : 0);
    out.p25.push(has ? quantile(values, 0.25) : 0);
    out.median.push(has ? quantile(values, 0.5) : 0);
    out.p75.push(has ? quantile(values, 0.75) : 0);
    out.max.push(has ? values[values.length - 1] : 0);
  }
  return out;
}

/**
 * A duration curve: the values sorted high to low, against the hours each
 * snapshot stands for summed (snapshot_weighting_generators), so a record
 * with uneven snapshots still spans the year.
 */
export function durationCurve(
  values: (number | null)[],
  weights: number[],
): { x: number[]; values: number[] } {
  const order = values
    .map((value, index) => ({ value, weight: weights[index] ?? 1 }))
    .filter(
      (entry): entry is { value: number; weight: number } =>
        entry.value !== null && Number.isFinite(entry.value),
    )
    .sort((a, b) => b.value - a.value);
  const x: number[] = [];
  let hours = 0;
  for (const entry of order) {
    hours += entry.weight;
    x.push(hours);
  }
  return { x, values: order.map((entry) => entry.value) };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "1 Jan 09:00" (UTC, as snapshots are stored). */
export function timeLabel(ms: number): string {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return String(ms);
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}`;
}

/** "2013-01-01 09:00", for CSV. */
export function timeIso(ms: number): string {
  const date = new Date(ms);
  return Number.isNaN(date.getTime())
    ? String(ms)
    : date.toISOString().slice(0, 16).replace("T", " ");
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const size = Math.abs(value);
  return value.toLocaleString(undefined, {
    maximumFractionDigits: size >= 100 ? 0 : size >= 10 ? 1 : size >= 1 ? 2 : 3,
  });
}

/** Downloads a CSV of a time axis and columns (wide: Time, then one column per series). */
export function downloadCsv(
  fileName: string,
  times: number[],
  columns: { header: string; values: (number | null)[] }[],
) {
  const quote = (text: string) => (/[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text);
  const lines = [["Time", ...columns.map((column) => column.header)].map(quote).join(",")];
  times.forEach((time, index) =>
    lines.push([timeIso(time), ...columns.map((column) => column.values[index] ?? "")].join(",")),
  );
  const href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = href;
  link.download = fileName.endsWith(".csv") ? fileName : `${fileName}.csv`;
  link.click();
  URL.revokeObjectURL(href);
}
