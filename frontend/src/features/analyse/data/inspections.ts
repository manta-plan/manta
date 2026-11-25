import type { InspectFilters } from "../lib/inspect-filters";
import type { WidgetSetItem } from "../lib/widget-sets";

/** One of the user's inspections: a page of widgets and its filters. */
export interface InspectionCanvas {
  id: string;
  name: string;
  description: string;
  items: WidgetSetItem[];
  filters?: InspectFilters;
}

/** What an inspection's page saves as the user works in it. */
export type InspectionContent = Pick<InspectionCanvas, "items" | "filters">;

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
    widgetIds: [
      "installed-capacity",
      "energy-capacity",
      "generator-supply",
      "withdrawal",
      "bus-price-map",
    ],
  },
  {
    id: "system-costs",
    name: "System Costs",
    description: "Where the money goes: capex and opex",
    widgetIds: ["cost-by-component", "cost-by-carrier"],
  },
  {
    id: "power-dispatch",
    name: "Power Dispatch",
    description: "Dispatch, demand and curtailment",
    widgetIds: ["dispatch-stack", "load", "curtailment"],
  },
  {
    id: "emissions",
    name: "Emissions & Policy",
    description: "CO2 by carrier",
    widgetIds: ["emissions-by-carrier"],
  },
  // Every built-in widget is a custom widget's query (builtInWidgetSpecs) of
  // the record's results. Widgets a custom widget can't express went, and
  // with them Transmission & Congestion and Hydrogen & Sector Coupling.
];

export function builtInInspection(id: string | null) {
  return BUILT_IN_INSPECTIONS.find((inspection) => inspection.id === id) ?? null;
}
