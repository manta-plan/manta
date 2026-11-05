import type { ResultCollection } from "../../project/data/result-collections";

export interface ResultChartPoint {
  label: string;
  value: number;
}

function hashString(text: string) {
  let hash = 0;
  for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) % 997;
  return hash;
}

// Dummy per-run variation of a collection's headline (last numeric) column
// — stands in for real solver output, deterministic per run (±6%) so two
// compared runs visibly differ, same idea as resultAreaValues for the map.
export function resultChartPoints(collection: ResultCollection, runId: string): ResultChartPoint[] {
  return collection.rows.map((row, rowIndex) => {
    const base =
      row
        .slice(1)
        .filter((cell): cell is number => typeof cell === "number")
        .at(-1) ?? 0;
    const adjustment = ((hashString(`${runId}:${collection.id}`) + rowIndex * 13) % 13) - 6;
    return { label: String(row[0]), value: Math.round(base * (1 + adjustment / 100) * 10) / 10 };
  });
}

export function resultChartValueLabel(collection: ResultCollection) {
  const index = collection.columns.findLastIndex(
    (_, columnIndex) =>
      columnIndex > 0 && collection.rows.some((row) => typeof row[columnIndex] === "number"),
  );
  return collection.columns[index] ?? "Value";
}

// Rounds out to a 1/2/5 × 10ⁿ step so a fixed shared axis still gets
// readable ticks.
function niceBound(value: number) {
  if (value === 0) return 0;
  const magnitude = 10 ** Math.floor(Math.log10(Math.abs(value)));
  const step = [1, 2, 5, 10].find((candidate) => candidate * magnitude >= Math.abs(value)) ?? 10;
  return Math.sign(value) * step * magnitude;
}

export function sharedChartBounds(...series: ResultChartPoint[][]): [number, number] {
  const values = series.flat().map((point) => point.value);
  if (values.length === 0) return [0, 1];
  return [niceBound(Math.min(0, ...values)), niceBound(Math.max(0, ...values)) || 1];
}
