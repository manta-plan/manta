// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import type { PeriodSpan } from "./periods";
import type { TimeWindow } from "./level-store";

export const DAY_MS = 24 * 3600 * 1000;
export const HOUR_MS = 3600 * 1000;
export const MIN_HOURS = 2;

export const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");

/** The season inside the period's span, as one window from its first to its last hour there; null when the span has none of it. */
export function seasonWindow(
  span: PeriodSpan,
  months: readonly number[],
  label: string,
): TimeWindow | null {
  const start = Date.parse(span.start);
  const end = Date.parse(span.end) + HOUR_MS;
  // Winter wraps the year: from December of the span's first year, else the span's start.
  let first: number | null = null;
  let last: number | null = null;
  for (let day = Math.floor(start / DAY_MS) * DAY_MS; day < end; day += DAY_MS) {
    if (!months.includes(new Date(day).getUTCMonth())) continue;
    first ??= Math.max(day, start);
    last = Math.min(day + DAY_MS, end);
  }
  if (first === null || last === null || last - first < MIN_HOURS * HOUR_MS) return null;
  return { start: iso(first), end: iso(last), label, months };
}
