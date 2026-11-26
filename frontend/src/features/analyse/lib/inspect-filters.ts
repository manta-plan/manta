import { createContext, useContext } from "react";

// Shared filters for the Analyse page: one set of period, bus and carrier
// filters applies to every widget of a view. A widget's query follows the
// ones it has a placeholder for ({{period}}, {{buses}}, {{carriers}}).

export type FilterDimension = "period" | "bus" | "carrier";

export const FILTER_DIMENSION_LABELS: Record<FilterDimension, string> = {
  period: "period",
  bus: "bus",
  carrier: "carrier",
};

export interface InspectFilters {
  /** One investment period (`'2030'`), or null for all of them. */
  period: string | null;
  buses: string[];
  carriers: string[];
}

export const EMPTY_FILTERS: InspectFilters = { period: null, buses: [], carriers: [] };

/** Filters as saved, which may predate a field. */
export function normalizeFilters(filters: Partial<InspectFilters> | undefined): InspectFilters {
  return {
    period: filters?.period ?? null,
    buses: filters?.buses ?? [],
    carriers: filters?.carriers ?? [],
  };
}

export function activeDimensions(filters: InspectFilters): FilterDimension[] {
  return [
    ...(filters.period !== null ? ["period" as const] : []),
    ...(filters.buses.length > 0 ? ["bus" as const] : []),
    ...(filters.carriers.length > 0 ? ["carrier" as const] : []),
  ];
}

export function describePeriod(period: string | null) {
  return period === null ? "All periods (an average year)" : period;
}

// Carrier groups an analyst would filter by. Each matches the carrier and
// technology labels the widgets use.
export const CARRIER_GROUPS: { id: string; label: string; color: string; match: string[] }[] = [
  {
    id: "solar",
    label: "Solar",
    color: "#f9d002",
    match: ["solar-pv-utility", "solar-pv-rooftop", "Solar PV", "solar"],
  },
  { id: "onwind", label: "Onshore wind", color: "#235ebc", match: ["Onshore Wind", "onwind"] },
  { id: "offwind", label: "Offshore wind", color: "#6895dd", match: ["offwind", "Offshore Wind"] },
  {
    id: "hydro",
    label: "Hydro",
    color: "#298c81",
    match: ["hydro", "run of river", "hydro-phs", "hydro-phs-pure", "Pumped Hydro"],
  },
  { id: "nuclear", label: "Nuclear", color: "#ff8c00", match: ["nuclear", "Nuclear", "uranium"] },
  {
    id: "gas",
    label: "Gas",
    color: "#e05b09",
    match: ["gas", "Gas CCGT", "gas boiler", "biogas", "CCGT", "OCGT"],
  },
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
