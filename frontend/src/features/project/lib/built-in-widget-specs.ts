import type { CustomQuery, Placeholder } from "./custom-query";
import type { CustomChart } from "./widget-sets";

// The built-in widgets a custom widget can rebuild, for their "Edit a copy"
// action: the query and chart that draw the same values from the result
// tables. Widgets with panels, dual axes or extra pickers aren't here yet.

export interface BuiltInWidgetSpec {
  query: CustomQuery;
  chart: CustomChart;
}

const follow = (...placeholders: Placeholder[]) =>
  placeholders.map((placeholder) => ({
    column: { buses: "bus", snapshots: "snapshot", carriers: "carrier" }[placeholder],
    placeholder,
  }));

const spec = (
  query: Omit<CustomQuery, "orderBy" | "limit"> & Partial<Pick<CustomQuery, "orderBy" | "limit">>,
  chart: CustomChart,
): BuiltInWidgetSpec => ({ query: { orderBy: null, limit: null, ...query }, chart });

export const BUILT_IN_WIDGET_SPECS: Record<string, BuiltInWidgetSpec> = {
  "generator-supply": spec(
    {
      table: "supply",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("buses", "snapshots", "carriers"),
    },
    "bar",
  ),
  withdrawal: spec(
    {
      table: "withdrawal",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("buses", "snapshots", "carriers"),
    },
    "bar",
  ),
  "bus-price-map": spec(
    {
      table: "prices",
      aggregate: "avg",
      groupBy: ["bus"],
      where: [...follow("buses", "snapshots"), { column: "carrier", values: ["AC"] }],
    },
    "map",
  ),
  "h2-price-map": spec(
    {
      table: "prices",
      aggregate: "avg",
      groupBy: ["bus"],
      where: [...follow("buses", "snapshots"), { column: "carrier", values: ["H2"] }],
    },
    "map",
  ),
  "cost-by-component": spec(
    {
      table: "component_costs",
      aggregate: "sum",
      groupBy: ["component", "cost_type"],
      where: follow("buses"),
    },
    "stacked-bar",
  ),
  "cost-by-carrier": spec(
    {
      table: "carrier_costs",
      aggregate: "sum",
      groupBy: ["carrier", "cost_type"],
      where: follow("buses", "carriers"),
    },
    "stacked-bar",
  ),
  "dispatch-stack": spec(
    {
      table: "dispatch",
      aggregate: "avg",
      groupBy: ["snapshot", "carrier"],
      where: follow("buses", "snapshots", "carriers"),
    },
    "area",
  ),
  curtailment: spec(
    {
      table: "curtailment",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("buses", "snapshots", "carriers"),
    },
    "bar",
  ),
  "emissions-by-sector": spec(
    {
      table: "emissions",
      aggregate: "sum",
      groupBy: ["sector"],
      where: follow("buses", "snapshots"),
    },
    "bar",
  ),
};
