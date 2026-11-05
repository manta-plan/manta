import { createContext, useCallback, useContext, useState } from "react";
import { DUMMY_RESULT_RUNS } from "../data/inspect-results";
import type { WidgetData, WidgetDataCell } from "./widget-data";

// How a widget learns which run result it draws, and how a built-in widget
// splits into two panels when the page compares results.
//
// The dummy values differ per result by a few percent per row: the first
// result matches the placeholders as written, so the built-ins and their
// custom copies agree on it, and every other result shifts consistently.

function hashString(text: string) {
  let hash = 0;
  for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) % 100003;
  return hash;
}

/** The dummy shift of one row (keyed by its labels) in one result. */
export function resultFactor(resultId: string, key: string) {
  if (resultId === DUMMY_RESULT_RUNS[0].id) return 1;
  return 1 + ((hashString(`${resultId}:${key}`) % 13) - 6) / 100;
}

/** Scales a placeholder value to one result; `key` names its row, e.g. a carrier. */
export type Vary = (key: string, value: number) => number;

export const ResultContext = createContext<string>(DUMMY_RESULT_RUNS[0].id);

/** Scales a placeholder value to the result being drawn; `key` names its row, e.g. a carrier. */
export function useResultVariation(): Vary {
  const resultId = useContext(ResultContext);
  return useCallback(
    (key: string, value: number) => value * resultFactor(resultId, key),
    [resultId],
  );
}

// ------------------------------------------------------------ Comparison

export interface ComparisonValue {
  /** The selected result's copy draws the card; the compared copy only its body. */
  role: "primary" | "comparison";
  primaryName: string;
  comparisonName: string;
  /** Where the compared copy renders its body: the card's right-hand panel. */
  slot: HTMLElement | null;
  setSlot: (element: HTMLElement | null) => void;
  comparisonData: WidgetData | null;
  setComparisonData: (data: WidgetData) => void;
  /** State both copies share, such as a picker's value or a map's viewport. */
  shared: Record<string, unknown>;
  setShared: (key: string, value: unknown) => void;
  /** Links both copies' charts: one hover, one value scale. */
  chartGroup: string;
}

export const ComparisonContext = createContext<ComparisonValue | null>(null);

export function useComparison() {
  return useContext(ComparisonContext);
}

/** useState, except that both copies of a compared widget read and write one value. */
export function useSharedWidgetState<T>(
  key: string,
  initial: T | (() => T),
): [T, (value: T) => void] {
  const comparison = useComparison();
  const [local, setLocal] = useState(initial);
  if (!comparison) return [local, setLocal];
  const value = key in comparison.shared ? (comparison.shared[key] as T) : local;
  return [value, (next: T) => comparison.setShared(key, next)];
}

const isNumberColumn = (data: WidgetData, column: number) =>
  data.rows.some((row) => typeof row[column] === "number");

/**
 * Both results' tables side by side: the label columns, then each value
 * column for the selected result, the compared one and their difference
 * (selected minus compared, as the custom widgets show it).
 */
export function compareWidgetData(
  primary: WidgetData,
  comparison: WidgetData,
  primaryName: string,
  comparisonName: string,
): WidgetData {
  const sameShape =
    primary.columns.length === comparison.columns.length &&
    primary.columns.every((column, index) => column === comparison.columns[index]);
  if (!sameShape) {
    // Different shapes can't line up, so stack them with a result column.
    return {
      columns: ["Result", ...primary.columns],
      rows: [
        ...primary.rows.map((row) => [primaryName, ...row]),
        ...comparison.rows.map((row) => [comparisonName, ...row.slice(0, primary.columns.length)]),
      ],
    };
  }
  const valueColumns = primary.columns
    .map((_, index) => index)
    .filter((index) => isNumberColumn(primary, index) || isNumberColumn(comparison, index));
  const labelColumns = primary.columns
    .map((_, index) => index)
    .filter((index) => !valueColumns.includes(index));
  const keyOf = (row: WidgetDataCell[]) =>
    labelColumns.map((index) => String(row[index] ?? "")).join("\u0000");
  const comparedByKey = new Map(comparison.rows.map((row) => [keyOf(row), row]));
  const primaryKeys = new Set(primary.rows.map(keyOf));
  const rows = [
    ...primary.rows,
    ...comparison.rows.filter((row) => !primaryKeys.has(keyOf(row))),
  ].map((row) => {
    const own = primaryKeys.has(keyOf(row)) ? row : null;
    const compared = comparedByKey.get(keyOf(row)) ?? null;
    return [
      ...labelColumns.map((index) => row[index]),
      ...valueColumns.flatMap((index) => {
        const a = own?.[index] ?? null;
        const b = compared?.[index] ?? null;
        const difference =
          typeof a === "number" && typeof b === "number" ? Math.round((a - b) * 1000) / 1000 : null;
        return [a, b, difference];
      }),
    ];
  });
  return {
    columns: [
      ...labelColumns.map((index) => primary.columns[index]),
      ...valueColumns.flatMap((index) => [
        `${primary.columns[index]} · ${primaryName}`,
        `${primary.columns[index]} · ${comparisonName}`,
        `${primary.columns[index]} · difference`,
      ]),
    ],
    rows,
  };
}
