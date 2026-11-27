// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { PLACEHOLDER_COLUMNS, type CustomQuery, type Placeholder } from "./custom-query";
import type { CustomChart } from "./widget-sets";

// The built-in widgets, as data: each is a custom widget's query and chart,
// with a title and subtitle. BuiltInWidget draws it with CustomWidget, and
// "Edit a copy" starts a custom widget from the same spec, so a built-in is
// always something a user could have built. A widget the custom widget
// can't express doesn't belong here.

export interface BuiltInWidgetSpec {
  label: string;
  subtitle: string;
  query: CustomQuery;
  chart: CustomChart;
}

const follow = (...placeholders: Placeholder[]) =>
  placeholders.map((placeholder) => ({ column: PLACEHOLDER_COLUMNS[placeholder], placeholder }));

const largestFirst = { orderBy: { by: "value", direction: "desc" } } as const;

const spec = (
  label: string,
  subtitle: string,
  query: Omit<CustomQuery, "orderBy" | "limit"> & Partial<Pick<CustomQuery, "orderBy" | "limit">>,
  chart: CustomChart,
): BuiltInWidgetSpec => ({
  label,
  subtitle,
  query: { orderBy: null, limit: null, ...query },
  chart,
});

// Every widget follows the period filter: energies and costs are a period's.
export const BUILT_IN_WIDGET_SPECS: Record<string, BuiltInWidgetSpec> = {
  // System Overview
  "installed-capacity": spec(
    "Installed capacity by component",
    "Optimised power capacity per component, stacked by carrier · links at their input",
    {
      table: "capacity",
      aggregate: "sum",
      groupBy: ["component", "carrier"],
      where: follow("period", "buses", "carriers"),
    },
    "stacked-bar",
  ),
  "energy-capacity": spec(
    "Storage energy capacity by carrier",
    "Optimised energy capacity of stores",
    {
      table: "energy_capacity",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("period", "buses", "carriers"),
      ...largestFirst,
    },
    "bar",
  ),
  "generator-supply": spec(
    "Generator supply by carrier",
    "Energy supplied by generators, largest first",
    {
      table: "supply",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("period", "buses", "carriers"),
      ...largestFirst,
    },
    "bar",
  ),
  withdrawal: spec(
    "Withdrawal by carrier",
    "Energy drawn by loads, largest first",
    {
      table: "withdrawal",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("period", "buses", "carriers"),
      ...largestFirst,
    },
    "bar",
  ),
  "bus-price-map": spec(
    "Time-averaged bus prices",
    "Hours-weighted average AC price at each bus",
    {
      table: "prices",
      aggregate: "avg",
      groupBy: ["bus"],
      where: [...follow("period", "buses"), { column: "carrier", values: ["AC"] }],
    },
    "map",
  ),
  // System Costs
  "cost-by-component": spec(
    "Annualised system cost by component",
    "Capital and operational expenditure",
    {
      table: "component_costs",
      aggregate: "sum",
      groupBy: ["component", "cost_type"],
      where: follow("period", "buses"),
    },
    "stacked-bar",
  ),
  "cost-by-carrier": spec(
    "System cost by carrier",
    "Ten most expensive carriers, capex and opex",
    {
      table: "carrier_costs",
      aggregate: "sum",
      groupBy: ["carrier", "cost_type"],
      where: follow("period", "buses", "carriers"),
      ...largestFirst,
      limit: 10,
    },
    "stacked-bar",
  ),
  // Power Dispatch
  "dispatch-stack": spec(
    "Dispatch by carrier",
    "Generators and storage units · charging below zero",
    {
      table: "dispatch",
      aggregate: "avg",
      groupBy: ["snapshot", "carrier"],
      where: follow("period", "buses", "carriers"),
    },
    "area",
  ),
  load: spec(
    "Electricity demand",
    "Power drawn by loads, on the same time axis as dispatch",
    {
      table: "load",
      aggregate: "avg",
      groupBy: ["snapshot"],
      where: follow("period", "buses", "carriers"),
    },
    "line",
  ),
  curtailment: spec(
    "Curtailment by carrier",
    "Available energy that was not used, largest first",
    {
      table: "curtailment",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("period", "buses", "carriers"),
      ...largestFirst,
    },
    "bar",
  ),
  // Emissions & Policy
  // Key figures: one number each, for reports.
  "total-cost": spec(
    "Total system cost",
    "Annualised capex and opex",
    { table: "component_costs", aggregate: "sum", groupBy: [], where: follow("period", "buses") },
    "number",
  ),
  "total-supply": spec(
    "Total generator supply",
    "Energy supplied by generators",
    {
      table: "supply",
      aggregate: "sum",
      groupBy: [],
      where: follow("period", "buses", "carriers"),
    },
    "number",
  ),
  "total-emissions": spec(
    "Total CO2 emissions",
    "From generators' fuel",
    {
      table: "emissions",
      aggregate: "sum",
      groupBy: [],
      where: follow("period", "buses", "carriers"),
    },
    "number",
  ),
  "total-curtailment": spec(
    "Total curtailment",
    "Available wind and solar energy not used",
    {
      table: "curtailment",
      aggregate: "sum",
      groupBy: [],
      where: follow("period", "buses", "carriers"),
    },
    "number",
  ),
  "emissions-by-carrier": spec(
    "CO2 emissions by carrier",
    "Generators' fuel use × the carrier's CO2 intensity, largest first",
    {
      table: "emissions",
      aggregate: "sum",
      groupBy: ["carrier"],
      where: follow("period", "buses", "carriers"),
      ...largestFirst,
    },
    "bar",
  ),
};
