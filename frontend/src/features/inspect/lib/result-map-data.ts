import { regionFeatures } from "../../project/lib/record-geo";
import type { ResultCollection } from "../../project/data/result-collections";
import type { LoadedRecord } from "../../project/store/types";

export interface ResultAreaValue {
  name: string;
  value: number;
}

// The record's regions, one area per location (a location with two regions
// shares its value between them).
export function resultAreas(record: LoadedRecord | null) {
  return regionFeatures(record);
}

function hashString(text: string) {
  let hash = 0;
  for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) % 100003;
  return hash;
}

// Dummy spatial split of a collection's headline total across the model's
// areas — stands in for real per-area solver output, deterministic per run
// so the same run always paints the same map and two runs visibly differ.
export function resultAreaValues(
  record: LoadedRecord | null,
  collection: ResultCollection,
  runId: string,
): ResultAreaValue[] {
  const areas = [
    ...new globalThis.Map(resultAreas(record).map((area) => [area.properties.name, area])).values(),
  ];
  if (areas.length === 0) return [];
  const total = collection.rows.reduce(
    (sum, row) =>
      sum + Math.abs(row.slice(1).find((cell): cell is number => typeof cell === "number") ?? 0),
    0,
  );
  const weights = areas.map(
    (area) => 0.4 + (hashString(`${runId}:${collection.id}:${area.properties.name}`) % 1000) / 1000,
  );
  const weightSum = weights.reduce((sum, weight) => sum + weight, 0);
  return areas.map((area, index) => ({
    name: area.properties.name,
    value: (total * weights[index]) / weightSum,
  }));
}

export function resultValueLabel(collection: ResultCollection) {
  return (
    collection.columns.find(
      (_, index) => index > 0 && collection.rows.some((row) => typeof row[index] === "number"),
    ) ?? "Value"
  );
}
