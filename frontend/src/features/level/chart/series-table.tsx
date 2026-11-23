// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useState } from "react";
import { useChartHeight } from "./use-chart-height";
import { formatNumber, timeLabel } from "./spec";

// The picked series as a table: one row per snapshot of the window ("Time"),
// one column per series. Read-only this round. Rows are virtualised: a year
// of hours is 8,760 of them.

const ROW = 24;
const HEIGHT = 260;
const OVERSCAN = 10;

export interface SeriesColumn {
  /** "<attribute> · <owner>". */
  label: string;
  unit: string;
  color: string;
  values: (number | null)[];
}

export function SeriesTable({ times, columns }: { times: number[]; columns: SeriesColumn[] }) {
  const [scrollTop, setScrollTop] = useState(0);
  const height = useChartHeight(HEIGHT);
  const first = Math.max(0, Math.floor(scrollTop / ROW) - OVERSCAN);
  const last = Math.min(times.length, Math.ceil((scrollTop + height) / ROW) + OVERSCAN);
  const cell = "border-b border-surface-700/60 px-3 whitespace-nowrap";
  return (
    <div
      className="border-surface-700 mx-3 my-2 overflow-auto border"
      style={{ height }}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
    >
      <table className="w-full border-collapse text-[11px]">
        <thead className="bg-surface-800 text-surface-400 sticky top-0 z-10 text-left">
          <tr>
            <th className="border-surface-600 bg-surface-800 sticky left-0 z-10 border-b px-3 py-1.5 font-medium">
              Time
            </th>
            {columns.map((column, index) => (
              <th
                key={index}
                className="border-surface-600 border-b px-3 py-1.5 text-right font-medium"
              >
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 shrink-0 rounded-sm"
                    style={{ backgroundColor: column.color }}
                  />
                  {column.label} <span className="text-surface-500">[{column.unit}]</span>
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {first > 0 && <tr style={{ height: first * ROW }} aria-hidden />}
          {times.slice(first, last).map((time, offset) => {
            const index = first + offset;
            return (
              <tr
                key={index}
                style={{ height: ROW }}
                className="text-surface-200 hover:bg-surface-800/60"
              >
                <td className={`bg-surface-900 text-surface-300 sticky left-0 font-mono ${cell}`}>
                  {timeLabel(time)}
                </td>
                {columns.map((column, columnIndex) => (
                  <td key={columnIndex} className={`text-right tabular-nums ${cell}`}>
                    {formatNumber(column.values[index])}
                  </td>
                ))}
              </tr>
            );
          })}
          {last < times.length && (
            <tr style={{ height: (times.length - last) * ROW }} aria-hidden />
          )}
        </tbody>
      </table>
    </div>
  );
}
