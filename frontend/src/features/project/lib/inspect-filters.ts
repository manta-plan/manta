import { createContext, useContext } from "react";

// Shared filters for the inspection page: one set of bus, snapshot and
// carrier filters applies to every view and widget. The results are dummy,
// so filtering only reshapes placeholder values — but it does so
// deterministically, so the same filter always paints the same numbers.

export type FilterDimension = "bus" | "snapshot" | "carrier";

export const FILTER_DIMENSION_LABELS: Record<FilterDimension, string> = {
  bus: "bus",
  snapshot: "snapshot",
  carrier: "carrier",
};

// A dummy hourly year. Hour 0 is 1 Jan 2040, 00:00.
export const SNAPSHOT_YEAR = 2040;
export const SNAPSHOT_COUNT = 8784; // 2040 is a leap year

export type SnapshotFilter =
  | { mode: "all" }
  | { mode: "single"; hour: number }
  | { mode: "range"; start: number; end: number };

export interface InspectFilters {
  buses: string[];
  snapshots: SnapshotFilter;
  carriers: string[];
}

export const EMPTY_FILTERS: InspectFilters = {
  buses: [],
  snapshots: { mode: "all" },
  carriers: [],
};

export function activeDimensions(filters: InspectFilters): FilterDimension[] {
  return [
    ...(filters.buses.length > 0 ? ["bus" as const] : []),
    ...(filters.snapshots.mode !== "all" ? ["snapshot" as const] : []),
    ...(filters.carriers.length > 0 ? ["carrier" as const] : []),
  ];
}

const HOUR_MS = 3_600_000;
const YEAR_START = Date.UTC(SNAPSHOT_YEAR, 0, 1);

export function snapshotDate(hour: number) {
  return new Date(YEAR_START + hour * HOUR_MS);
}

export function hourOfDate(date: Date) {
  return Math.min(
    SNAPSHOT_COUNT - 1,
    Math.max(0, Math.round((date.getTime() - YEAR_START) / HOUR_MS)),
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function snapshotLabel(hour: number) {
  const date = snapshotDate(hour);
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${String(date.getUTCHours()).padStart(2, "0")}:00`;
}

// Value for <input type="datetime-local">, in the snapshot calendar (UTC).
export function snapshotInputValue(hour: number) {
  return snapshotDate(hour).toISOString().slice(0, 16);
}

export function hourFromInputValue(value: string) {
  return hourOfDate(new Date(`${value}:00Z`));
}

export function snapshotRange(filter: SnapshotFilter): [number, number] {
  if (filter.mode === "all") return [0, SNAPSHOT_COUNT - 1];
  if (filter.mode === "single") return [filter.hour, filter.hour];
  return [Math.min(filter.start, filter.end), Math.max(filter.start, filter.end)];
}

export function snapshotCount(filter: SnapshotFilter) {
  const [start, end] = snapshotRange(filter);
  return end - start + 1;
}

const dayStart = (month: number, day: number) =>
  hourOfDate(new Date(Date.UTC(SNAPSHOT_YEAR, month, day)));

export const SNAPSHOT_PRESETS: { label: string; filter: SnapshotFilter }[] = [
  {
    label: "Winter peak week",
    filter: { mode: "range", start: dayStart(0, 16), end: dayStart(0, 23) - 1 },
  },
  {
    label: "Summer week",
    filter: { mode: "range", start: dayStart(6, 9), end: dayStart(6, 16) - 1 },
  },
  { label: "Hour of max load", filter: { mode: "single", hour: dayStart(0, 18) + 18 } },
  { label: "April", filter: { mode: "range", start: dayStart(3, 1), end: dayStart(4, 1) - 1 } },
];

export function describeSnapshots(filter: SnapshotFilter) {
  if (filter.mode === "all") return "All snapshots";
  if (filter.mode === "single") return snapshotLabel(filter.hour);
  const [start, end] = snapshotRange(filter);
  return `${snapshotLabel(start)} – ${snapshotLabel(end)}`;
}

// Carrier groups an analyst would filter by. Each matches the carrier and
// technology labels the dummy widgets use.
export const CARRIER_GROUPS: { id: string; label: string; color: string; match: string[] }[] = [
  {
    id: "solar",
    label: "Solar",
    color: "#f9d002",
    match: ["solar-pv-utility", "solar-pv-rooftop", "Solar PV", "solar"],
  },
  { id: "onwind", label: "Onshore wind", color: "#235ebc", match: ["Onshore Wind", "onwind"] },
  {
    id: "offwind",
    label: "Offshore wind",
    color: "#6895dd",
    match: [
      "offwind-ac",
      "offwind-dc",
      "offwind-ac-fb-r",
      "offwind-dc-fb-oh",
      "offwind-dc-fl-oh",
      "Offshore Wind",
    ],
  },
  {
    id: "hydro",
    label: "Hydro",
    color: "#298c81",
    match: ["hydro", "run of river", "hydro-phs", "hydro-phs-pure", "Pumped Hydro"],
  },
  { id: "nuclear", label: "Nuclear", color: "#ff8c00", match: ["nuclear", "Nuclear", "uranium"] },
  { id: "gas", label: "Gas", color: "#e05b09", match: ["gas", "Gas CCGT", "gas boiler", "biogas"] },
  { id: "coal", label: "Coal & lignite", color: "#545454", match: ["coal", "Coal", "lignite"] },
  {
    id: "oil",
    label: "Oil",
    color: "#aaaaaa",
    match: ["oil", "oil primary", "land transport oil", "shipping oil", "kerosene for aviation"],
  },
  {
    id: "biomass",
    label: "Biomass",
    color: "#dd88cc",
    match: ["biomass", "solid biomass", "biomass final energy demand"],
  },
  {
    id: "hydrogen",
    label: "Hydrogen",
    color: "#bf13a0",
    match: [
      "H2",
      "H2 Store",
      "H2 pipeline",
      "H2 Electrolysis",
      "import H2",
      "H2 exogenous demand",
      "Fischer-Tropsch",
    ],
  },
  {
    id: "battery",
    label: "Battery",
    color: "#ace37f",
    match: ["Battery Storage", "home battery", "battery"],
  },
  {
    id: "grid",
    label: "Grid",
    color: "#70af1d",
    match: ["AC", "DC", "electricity distribution grid", "electricity"],
  },
];

const GROUP_BY_LABEL = new Map(
  CARRIER_GROUPS.flatMap((group) =>
    group.match.map((label) => [label.toLowerCase(), group.id] as const),
  ),
);

export function carrierGroupOf(label: string): string | null {
  const key = label.toLowerCase();
  const exact = GROUP_BY_LABEL.get(key);
  if (exact) return exact;
  // Labels like "Battery Fleet — North" or "Pumped Hydro — Site A".
  return (
    CARRIER_GROUPS.find((group) => group.match.some((match) => key.startsWith(match.toLowerCase())))
      ?.id ?? null
  );
}

/** Whether a carrier-labelled row survives the carrier filter. */
export function carrierAllowed(filters: InspectFilters, label: string) {
  if (filters.carriers.length === 0) return true;
  const group = carrierGroupOf(label);
  return group !== null && filters.carriers.includes(group);
}

function hashString(text: string) {
  let hash = 0;
  for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) % 100003;
  return hash;
}

/** A bus's relative size, for splitting system totals across buses. */
export function busWeight(bus: string) {
  return 0.4 + (hashString(bus) % 1000) / 1000;
}

/** Share of the system the selected buses stand for (1 with no bus filter). */
export function busShare(filters: InspectFilters, allBuses: string[]) {
  if (filters.buses.length === 0 || allBuses.length === 0) return 1;
  const total = allBuses.reduce((sum, bus) => sum + busWeight(bus), 0);
  const selected = filters.buses.reduce((sum, bus) => sum + busWeight(bus), 0);
  return Math.min(1, selected / total);
}

// Seasonal shape per carrier group: solar peaks in summer, wind and heating
// demand in winter. 1 is the yearly average.
export function seasonalFactor(hour: number, group: string | null) {
  const season = Math.cos(2 * Math.PI * (hour / SNAPSHOT_COUNT) - 0.1); // 1 mid-winter, -1 mid-summer
  const hourOfDay = hour % 24;
  if (group === "solar")
    return Math.max(0, Math.sin(((hourOfDay - 6) / 12) * Math.PI)) * Math.PI * (1 - 0.45 * season);
  if (group === "onwind" || group === "offwind") return 1 + 0.35 * season;
  if (group === "gas" || group === "coal") return 1 + 0.3 * season;
  return 1 + 0.15 * season;
}

/**
 * Share of a yearly energy total that falls in hours start–end, with a
 * seasonal shape for the label's carrier (1 for the whole year).
 */
export function hourRangeShare(start: number, end: number, label?: string) {
  if (start <= 0 && end >= SNAPSHOT_COUNT - 1) return 1;
  const group = label ? carrierGroupOf(label) : null;
  // Sample at most ~500 hours so long ranges stay cheap.
  const step = Math.max(1, Math.floor((end - start + 1) / 500));
  let sum = 0;
  let samples = 0;
  for (let hour = start; hour <= end; hour += step) {
    sum += seasonalFactor(hour, group);
    samples += 1;
  }
  return (sum / samples) * ((end - start + 1) / SNAPSHOT_COUNT);
}

/** Share of a yearly energy total that falls in the selected snapshots (1 with no snapshot filter). */
export function snapshotShare(filters: InspectFilters, label?: string) {
  if (filters.snapshots.mode === "all") return 1;
  const [start, end] = snapshotRange(filters.snapshots);
  return hourRangeShare(start, end, label);
}

/** Seasonal level (1 = yearly average) for prices and other per-hour values. */
export function snapshotLevel(filters: InspectFilters, label?: string) {
  if (filters.snapshots.mode === "all") return 1;
  return snapshotShare(filters, label) / (snapshotCount(filters.snapshots) / SNAPSHOT_COUNT);
}

export type ValueKind = "energy" | "capacity" | "ratio";

// Reads a column header's unit: energy totals follow the snapshots and
// buses, capacities only the buses, and percentages neither.
export function valueKindOf(header: string): ValueKind {
  if (/%|€\/|eff\.|factor/i.test(header)) return "ratio";
  if (/\b(GWh|TWh|MWh|Mt|kt|cycles)\b/i.test(header)) return "energy";
  return "capacity";
}

export function scaleValue(
  filters: InspectFilters,
  allBuses: string[],
  value: number,
  kind: ValueKind,
  label?: string,
) {
  if (kind === "ratio") return value;
  const scaled =
    value * busShare(filters, allBuses) * (kind === "energy" ? snapshotShare(filters, label) : 1);
  // Three significant digits, so one hour's share of a yearly total doesn't round to 0.
  return Math.abs(scaled) >= 100 ? Math.round(scaled * 10) / 10 : Number(scaled.toPrecision(3));
}

export interface InspectFilterContextValue {
  filters: InspectFilters;
  /** Every bus filters can pick from, for bus shares. */
  allBuses: string[];
}

export const InspectFilterContext = createContext<InspectFilterContextValue>({
  filters: EMPTY_FILTERS,
  allBuses: [],
});

export function useInspectFilters() {
  return useContext(InspectFilterContext);
}

// The Custom views' collections: rows labelled by a carrier or technology
// follow the carrier filter, and every value follows its column's unit.
type Collection = { columns: string[]; rows: (string | number)[][] };

function isCarrierLabelled(collection: Collection) {
  return collection.rows.every((row) => carrierGroupOf(String(row[0])) !== null);
}

export function collectionFilteredBy(collection: Collection): FilterDimension[] {
  return [
    "bus",
    ...(collection.columns.slice(1).some((column) => valueKindOf(column) === "energy")
      ? ["snapshot" as const]
      : []),
    ...(isCarrierLabelled(collection) ? ["carrier" as const] : []),
  ];
}

export function filterCollection<T extends Collection>(
  collection: T,
  filters: InspectFilters,
  allBuses: string[],
): T {
  if (activeDimensions(filters).length === 0) return collection;
  const kinds = collection.columns.map(valueKindOf);
  const rows = (
    isCarrierLabelled(collection)
      ? collection.rows.filter((row) => carrierAllowed(filters, String(row[0])))
      : collection.rows
  ).map((row) =>
    row.map((cell, index) =>
      index > 0 && typeof cell === "number"
        ? scaleValue(filters, allBuses, cell, kinds[index], String(row[0]))
        : cell,
    ),
  );
  return { ...collection, rows };
}
