import {
  COST_BY_CARRIER,
  COST_BY_COMPONENT,
  CURTAILMENT,
  EMISSIONS_BY_SECTOR,
  GENERATOR_SUPPLY,
  WITHDRAWAL,
  busPrice,
} from "./inspect-dummy-data";
import { STACK_ORDER } from "../lib/dispatch-simulation";

// The result tables a custom widget queries, as a run result would expose
// them: one long table per output, a column per dimension plus `value`.
// Dummy: rows are generated from the same placeholders the built-in widgets
// draw, so nothing here is solver output.
//
// `bus` and `snapshot` columns span the record's buses and the 2040 hourly
// year; every other column lists its labels in `rows`.

/**
 * How a row's value behaves over buses and hours:
 * - energy: `base` is the yearly system total, split over buses by size
 *   and over hours by the carrier's seasonal shape.
 * - price: `base` is unused; each bus has its own price, which follows the
 *   carrier's seasonal shape.
 * - power: the dispatch simulation's GW for the row's carrier, split over
 *   buses by size.
 * - static: `base` is a system total with no time dimension (annualised
 *   costs), split over buses by size.
 */
export type ResultValueKind = "energy" | "price" | "power" | "static";

export interface ResultTableRow {
  labels: Record<string, string>;
  base: number;
}

export interface ResultTable {
  name: string;
  label: string;
  description: string;
  /** Unit of `value`. */
  unit: string;
  /** What `value` measures, for axis names: "Supply", "Price". */
  valueLabel: string;
  /** Dimension columns, in the order a query lists them. */
  columns: string[];
  kind: ResultValueKind;
  /** The column whose label gives a row its seasonal shape and carrier group. */
  shapeColumn?: string;
  rows: ResultTableRow[];
}

const pairRows = (column: string, rows: [string, number][]): ResultTableRow[] =>
  rows.map(([label, base]) => ({ labels: { [column]: label }, base }));

const costRows = (column: string, rows: [string, number, number][]): ResultTableRow[] =>
  rows.flatMap(([label, capex, opex]) => [
    { labels: { [column]: label, cost_type: "Capex" }, base: capex },
    { labels: { [column]: label, cost_type: "Opex" }, base: opex },
  ]);

export const RESULT_TABLES: ResultTable[] = [
  {
    name: "supply",
    label: "Supply",
    description: "Energy supplied by generators, per carrier",
    unit: "TWh",
    valueLabel: "Supply",
    columns: ["snapshot", "bus", "carrier"],
    kind: "energy",
    shapeColumn: "carrier",
    rows: pairRows("carrier", GENERATOR_SUPPLY),
  },
  {
    name: "withdrawal",
    label: "Withdrawal",
    description: "Energy drawn by loads and negative generators, per carrier",
    unit: "TWh",
    valueLabel: "Withdrawal",
    columns: ["snapshot", "bus", "carrier"],
    kind: "energy",
    shapeColumn: "carrier",
    rows: pairRows("carrier", WITHDRAWAL),
  },
  {
    name: "dispatch",
    label: "Dispatch",
    description: "Hourly power output per carrier; charging and electrolysis are negative",
    unit: "GW",
    valueLabel: "Power",
    columns: ["snapshot", "bus", "carrier"],
    kind: "power",
    shapeColumn: "carrier",
    rows: STACK_ORDER.map((carrier) => ({ labels: { carrier }, base: 0 })),
  },
  {
    name: "prices",
    label: "Bus prices",
    description: "Marginal price at each bus, per bus carrier",
    unit: "€/MWh",
    valueLabel: "Price",
    columns: ["snapshot", "bus", "carrier"],
    kind: "price",
    shapeColumn: "carrier",
    rows: ["AC", "H2"].map((carrier) => ({ labels: { carrier }, base: 0 })),
  },
  {
    name: "curtailment",
    label: "Curtailment",
    description: "Available energy that was not used, per carrier",
    unit: "TWh",
    valueLabel: "Curtailment",
    columns: ["snapshot", "bus", "carrier"],
    kind: "energy",
    shapeColumn: "carrier",
    rows: CURTAILMENT.map(([carrier, energy]) => ({ labels: { carrier }, base: energy })),
  },
  {
    name: "emissions",
    label: "Emissions",
    description: "CO2 emitted per sector; removals are negative",
    unit: "Mt CO2",
    valueLabel: "Emissions",
    columns: ["snapshot", "bus", "sector"],
    kind: "energy",
    shapeColumn: "sector",
    rows: pairRows("sector", EMISSIONS_BY_SECTOR),
  },
  {
    name: "component_costs",
    label: "Costs by component",
    description: "Annualised capital and operational expenditure per component",
    unit: "bn €/a",
    valueLabel: "Cost",
    columns: ["bus", "component", "cost_type"],
    kind: "static",
    rows: costRows("component", COST_BY_COMPONENT),
  },
  {
    name: "carrier_costs",
    label: "Costs by carrier",
    description: "Annualised capital and operational expenditure per carrier",
    unit: "bn €/a",
    valueLabel: "Cost",
    columns: ["bus", "carrier", "cost_type"],
    kind: "static",
    shapeColumn: "carrier",
    rows: costRows("carrier", COST_BY_CARRIER),
  },
];

export function resultTable(name: string): ResultTable | undefined {
  return RESULT_TABLES.find((table) => table.name === name);
}

/** A row's value at one bus (or the whole system) for price tables. */
export function rowBusPrice(row: ResultTableRow, bus: string) {
  return busPrice(bus, row.labels.carrier ?? "AC");
}
