import type { InspectFilters } from "../lib/inspect-filters";
import type { WidgetSetItem } from "../lib/widget-sets";

/** One of the user's inspections: a page of widgets and what it was last pointed at. */
export interface InspectionCanvas {
  id: string;
  name: string;
  description: string;
  items: WidgetSetItem[];
  resultId?: string;
  comparisonResultId?: string;
  filters?: InspectFilters;
  /** Legacy: the run an inspection reviewed before results went dummy. */
  runId?: string;
}

/** What an inspection's page saves as the user works in it. */
export type InspectionContent = Pick<
  InspectionCanvas,
  "items" | "resultId" | "comparisonResultId" | "filters"
>;

// Built-in inspections: fixed pages every project has. They can be edited
// for the session, and saved as one of the user's own.
export interface BuiltInInspection {
  id: string;
  name: string;
  description: string;
  widgetIds: string[];
}

export const BUILT_IN_INSPECTIONS: BuiltInInspection[] = [
  {
    id: "system-overview",
    name: "System Overview",
    description: "Capacity, supply, withdrawal and prices across the system",
    widgetIds: ["installed-capacity", "generator-supply", "withdrawal", "bus-price-map"],
  },
  {
    id: "system-costs",
    name: "System Costs",
    description: "Where the money goes: capex, opex and market value",
    widgetIds: [
      "cost-by-component",
      "cost-by-carrier",
      "lcoe-vs-market-value",
      "capacity-expansion",
    ],
  },
  {
    id: "power-dispatch",
    name: "Power Dispatch",
    description: "Hourly dispatch, storage, curtailment and prices",
    widgetIds: ["dispatch-stack", "storage-soc", "curtailment", "price-duration"],
  },
  {
    id: "transmission",
    name: "Transmission & Congestion",
    description: "Line loading, congestion and cross-border flows",
    widgetIds: ["line-loading-map", "congestion-hours", "cross-border-flows", "price-spread"],
  },
  {
    id: "emissions",
    name: "Emissions & Policy",
    description: "CO2 by sector, the limit and its shadow price",
    widgetIds: ["emissions-by-sector", "emissions-vs-cap", "co2-price", "fossil-fuel-use"],
  },
  // Hydrogen & Sector Coupling is out for now (modeller feedback). Its widgets
  // stay in the registry so saved inspections holding them still open.
];

export function builtInInspection(id: string | null) {
  return BUILT_IN_INSPECTIONS.find((inspection) => inspection.id === id) ?? null;
}
