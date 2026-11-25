// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { Level } from "../level";
import type { LevelQueryScope } from "../level-sql";
import {
  loadAvailable,
  loadAxis,
  loadAttributeAggregate,
  loadCapacity,
  loadLines,
  loadMeanPrice,
  loadOptimisedMix,
  loadPeakByLocation,
  loadPower,
  loadStateOfCharge,
  loadTotalLoad,
  type Axis,
  type CategoryValue,
} from "./chart-sql";
import { ACCENT, durationCurve, NEUTRAL, type ChartSpec, type SpecSeries } from "./spec";

// The standard charts of each level (the handover's table, a starting
// default until a settings page configures them): inputs everywhere, run
// results on Inspect. A statistic is known by its base name, which stays
// chosen across levels that have one of that name; "Starting"/"Actual"
// statistics read existing capacity in Build and optimised capacity in a
// run result.

export interface CarrierLook {
  name: string;
  color: string;
}

export interface StatisticContext {
  scope: LevelQueryScope;
  /** A run result is shown: results are there, and "Actual" reads optimised capacity. */
  inspect: boolean;
  carrier: (carrier: string | null) => CarrierLook;
  /** marginal_price's unit, as the record states it. */
  priceUnit: string;
}

export interface Statistic {
  /** The name without "Starting"/"Actual": what's kept across levels. */
  base: string;
  /** What the dropdown says. */
  label: string;
  /** What it shows, under the chart. */
  note: string;
  /** Needs a run result. */
  result: boolean;
  load: (context: StatisticContext) => Promise<ChartSpec | null>;
}

const GW = 1e-3;
const WIND_SOLAR = "#f2c94c";
const RED = "#e06c5b";

const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);
const scale = (values: (number | null)[], factor: number) =>
  values.map((value) => (value === null ? null : value * factor));
const minus = (a: (number | null)[], b: (number | null)[]) =>
  a.map((value, index) => (value === null ? null : value - (b[index] ?? 0)));
const total = (values: (number | null)[]) =>
  values.reduce<number>((sum, value) => sum + Math.abs(value ?? 0), 0);

/** Per-carrier series, largest first so the steadiest sit at the bottom of a stack; empty carriers dropped. */
function carrierSeries(
  lists: Map<string, (number | null)[]>,
  look: StatisticContext["carrier"],
  factor: number,
): SpecSeries[] {
  return [...lists.entries()]
    .map(([carrier, values]) => ({ ...look(carrier || null), values: scale(values, factor) }))
    .filter((series) => total(series.values) > 0)
    .sort((a, b) => total(b.values) - total(a.values));
}

function timeSpec(
  axis: Axis,
  unit: string,
  series: SpecSeries[],
  stacked = false,
): ChartSpec | null {
  if (series.length === 0 || axis.times.length === 0) return null;
  return { kind: "time", unit, times: axis.times, series, stacked };
}

/** One line, or one series per carrier stacked: a carrier level shows its one carrier as a line. */
function byCarrierSpec(
  axis: Axis,
  unit: string,
  lists: Map<string, (number | null)[]>,
  context: StatisticContext,
  factor: number,
  stacked: boolean,
): ChartSpec | null {
  const series = carrierSeries(lists, context.carrier, factor);
  return timeSpec(axis, unit, series, stacked && series.length > 1);
}

function durationSpec(
  axis: Axis,
  unit: string,
  name: string,
  values: (number | null)[] | null,
  color = ACCENT,
): ChartSpec | null {
  if (!values) return null;
  const curve = durationCurve(values, axis.weights);
  if (curve.values.length === 0) return null;
  return {
    kind: "duration",
    unit,
    xName: "Hours",
    x: curve.x,
    series: [{ name, color, values: curve.values }],
  };
}

function categoryBars(
  rows: CategoryValue[],
  unit: string,
  context: StatisticContext,
  colorBy: "carrier" | "none",
  factor = 1,
): ChartSpec | null {
  if (rows.length === 0) return null;
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  return {
    kind: "bar",
    unit,
    categories: sorted.map((row) =>
      colorBy === "carrier" ? context.carrier(row.category).name : (row.category ?? "(none)"),
    ),
    series: [{ name: unit, color: ACCENT, values: sorted.map((row) => row.value * factor) }],
    barColors:
      colorBy === "carrier" ? sorted.map((row) => context.carrier(row.category).color) : undefined,
  };
}

/** Bars per category (in name order), stacked by carrier. */
function stackedBars(
  rows: CategoryValue[],
  unit: string,
  context: StatisticContext,
  factor: number,
  label?: (category: string) => string,
): ChartSpec | null {
  if (rows.length === 0) return null;
  const categoryTotal = new Map<string, number>();
  const carrierTotal = new Map<string, number>();
  for (const row of rows) {
    const category = row.category ?? "(none)";
    categoryTotal.set(category, (categoryTotal.get(category) ?? 0) + row.value);
    carrierTotal.set(row.carrier ?? "", (carrierTotal.get(row.carrier ?? "") ?? 0) + row.value);
  }
  const categories = [...categoryTotal.keys()].sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  );
  const carriers = [...carrierTotal.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([carrier]) => carrier);
  return {
    kind: "bar",
    unit,
    stacked: true,
    categories: categories.map((category) => (label ? label(category) : category)),
    series: carriers.map((carrier) => {
      const look = context.carrier(carrier || null);
      const values = categories.map((category) =>
        rows
          .filter(
            (row) => (row.category ?? "(none)") === category && (row.carrier ?? "") === carrier,
          )
          .reduce((sum, row) => sum + row.value * factor, 0),
      );
      return { name: look.name, color: look.color, values };
    }),
  };
}

// ------------------------------------------------------------ The statistics

/** Starting in Build, Actual on a run result. */
function qualified(base: string, inspect: boolean) {
  return `${inspect ? "Actual" : "Starting"} ${lowerFirst(base)}`;
}

function input(base: string, note: string, load: Statistic["load"]): Statistic {
  return { base, label: base, note, result: false, load };
}

function capacityStatistic(
  base: string,
  inspect: boolean,
  note: string,
  load: Statistic["load"],
): Statistic {
  return { base, label: qualified(base, inspect), note, result: false, load };
}

function result(base: string, note: string, load: Statistic["load"]): Statistic {
  return { base, label: base, note, result: true, load };
}

const capUnit = (ctype: string) =>
  ctype === "Store" ? "MWh" : ctype === "Line" || ctype === "Transformer" ? "MVA" : "MW";
const capName = (ctype: string, inspect: boolean) => {
  const name =
    ctype === "Store" ? "e_nom" : ctype === "Line" || ctype === "Transformer" ? "s_nom" : "p_nom";
  return inspect ? `${name}_opt` : name;
};

async function loadVsRenewables(
  context: StatisticContext,
  withResidual: "none" | "starting" | "actual",
): Promise<ChartSpec | null> {
  const { scope } = context;
  const actual = withResidual === "actual" || (withResidual === "none" && context.inspect);
  const [axis, load, vre] = await Promise.all([
    loadAxis(scope),
    loadTotalLoad(scope),
    actual
      ? loadPower(scope, ["Generator"], { byCarrier: false, vreOnly: true })
      : loadAvailable(scope, { optimised: false, vreOnly: true, byCarrier: false }),
  ]);
  const loadValues = load ?? axis.times.map(() => 0);
  const vreValues = vre.get("all") ?? axis.times.map(() => 0);
  if (withResidual !== "none") {
    return timeSpec(axis, "GW", [
      {
        name: withResidual === "actual" ? "Actual residual load" : "Starting residual load",
        color: ACCENT,
        values: scale(minus(loadValues, vreValues), GW),
      },
    ]);
  }
  return timeSpec(axis, "GW", [
    { name: "Load", color: NEUTRAL, values: scale(loadValues, GW) },
    {
      name: actual ? "Wind and solar dispatched" : "Wind and solar available",
      color: WIND_SOLAR,
      values: scale(vreValues, GW),
    },
  ]);
}

async function availableGeneration(
  context: StatisticContext,
  byCarrier: boolean,
): Promise<ChartSpec | null> {
  const [axis, lists] = await Promise.all([
    loadAxis(context.scope),
    loadAvailable(context.scope, { optimised: context.inspect, vreOnly: false, byCarrier }),
  ]);
  return byCarrierSpec(axis, "GW", lists, context, GW, byCarrier);
}

async function dispatch(
  context: StatisticContext,
  ctypes: string[],
  byCarrier: boolean,
  stacked: boolean,
): Promise<ChartSpec | null> {
  const [axis, lists] = await Promise.all([
    loadAxis(context.scope),
    loadPower(context.scope, ctypes, { byCarrier }),
  ]);
  return byCarrierSpec(axis, "GW", lists, context, GW, stacked);
}

async function loadDuration(context: StatisticContext): Promise<ChartSpec | null> {
  const [axis, load] = await Promise.all([loadAxis(context.scope), loadTotalLoad(context.scope)]);
  return durationSpec(axis, "GW", "Load", load && scale(load, GW), NEUTRAL);
}

async function totalLoad(context: StatisticContext): Promise<ChartSpec | null> {
  const [axis, load] = await Promise.all([loadAxis(context.scope), loadTotalLoad(context.scope)]);
  return load
    ? timeSpec(axis, "GW", [{ name: "Load", color: NEUTRAL, values: scale(load, GW) }])
    : null;
}

async function meanPrice(
  context: StatisticContext,
  duration: boolean,
  name: string,
): Promise<ChartSpec | null> {
  const [axis, price] = await Promise.all([loadAxis(context.scope), loadMeanPrice(context.scope)]);
  if (duration) return durationSpec(axis, context.priceUnit, name, price);
  return price ? timeSpec(axis, context.priceUnit, [{ name, color: ACCENT, values: price }]) : null;
}

async function stateOfCharge(
  context: StatisticContext,
  ctype: "Store" | "StorageUnit",
  carrierLike: string | null,
): Promise<ChartSpec | null> {
  const [axis, lists] = await Promise.all([
    loadAxis(context.scope),
    loadStateOfCharge(context.scope, ctype, carrierLike),
  ]);
  return byCarrierSpec(axis, "GWh", lists, context, GW, true);
}

async function curtailment(context: StatisticContext): Promise<ChartSpec | null> {
  const { scope } = context;
  const [axis, available, dispatched] = await Promise.all([
    loadAxis(scope),
    loadAvailable(scope, { optimised: true, vreOnly: true, byCarrier: false }),
    loadPower(scope, ["Generator"], { byCarrier: false, vreOnly: true }),
  ]);
  const a = available.get("all");
  if (!a) return null;
  const d = dispatched.get("all") ?? [];
  return timeSpec(axis, "GW", [
    {
      name: "Curtailed",
      color: RED,
      values: a.map((value, index) =>
        value === null ? null : Math.max(0, value - (d[index] ?? 0)) * GW,
      ),
    },
  ]);
}

async function availabilityDuration(context: StatisticContext): Promise<ChartSpec | null> {
  const [axis, lists] = await Promise.all([
    loadAxis(context.scope),
    loadAttributeAggregate(
      context.scope,
      { ctype: "Generator", attribute: "p_max_pu", dim: "entity", optimised: context.inspect },
      "weighted",
    ),
  ]);
  return durationSpec(axis, "per unit", "p_max_pu", lists.get("value") ?? null);
}

async function capacityBars(
  context: StatisticContext,
  ctypes: string[] | null,
  by: "carrier" | "location",
  unit: string,
): Promise<ChartSpec | null> {
  const rows = await loadCapacity(context.scope, { ctypes, by, optimised: context.inspect });
  return categoryBars(rows, unit, context, by === "carrier" ? "carrier" : "none");
}

async function optimisedMix(
  context: StatisticContext,
  what: "capacity" | "output",
  by: "ctype" | "bus" | "bus-ctype",
): Promise<ChartSpec | null> {
  const rows = await loadOptimisedMix(context.scope, what, by);
  const unitLabel = (ctype: string) =>
    what === "capacity" && ctype === "Store"
      ? "Store (GWh)"
      : what === "capacity" && (ctype === "Line" || ctype === "Transformer")
        ? `${ctype} (GVA)`
        : ctype;
  return stackedBars(
    rows,
    what === "capacity" ? "GW" : "GWh",
    context,
    GW,
    by === "ctype" ? unitLabel : undefined,
  );
}

async function lineBars(context: StatisticContext): Promise<ChartSpec | null> {
  const lines = (await loadLines(context.scope, { optimised: context.inspect }))
    .filter((line) => line.capacity !== null)
    .sort((a, b) => (b.capacity ?? 0) - (a.capacity ?? 0))
    .slice(0, 12);
  if (lines.length === 0) return null;
  return {
    kind: "bar",
    unit: "MVA",
    categories: lines.map((line) => line.entity),
    series: [{ name: "MVA", color: NEUTRAL, values: lines.map((line) => line.capacity) }],
  };
}

async function lineRanks(
  context: StatisticContext,
  what: "length" | "loading",
): Promise<ChartSpec | null> {
  const lines = await loadLines(context.scope, { optimised: what === "loading" });
  const values = lines
    .map((line) =>
      what === "length" ? line.length : line.loading === null ? null : line.loading * 100,
    )
    .filter((value): value is number => value !== null && Number.isFinite(value));
  if (values.length === 0) return null;
  values.sort((a, b) => b - a);
  return {
    kind: "duration",
    unit: what === "length" ? "km" : "%",
    xName: "Lines",
    x: values.map((_, index) => index + 1),
    series: [
      {
        name: what === "length" ? "length" : "loading",
        color: what === "length" ? NEUTRAL : RED,
        values,
      },
    ],
  };
}

function capacityStatistics(
  level: Level,
  ctype: string | null,
  inspect: boolean,
  ctypes: string[] | null,
): Statistic[] {
  const unit = ctype ? capUnit(ctype) : "MW";
  const name = ctype ? capName(ctype, inspect) : inspect ? "p_nom_opt" : "p_nom";
  const out: Statistic[] = [];
  if (level.kind !== "carrier")
    out.push(
      capacityStatistic("Capacity by carrier", inspect, `${name} per carrier, ${unit}`, (context) =>
        capacityBars(context, ctypes, "carrier", unit),
      ),
    );
  out.push(
    capacityStatistic(
      "Capacity by location",
      inspect,
      `${name}, the 12 largest locations, ${unit}`,
      (context) => capacityBars(context, ctypes, "location", unit),
    ),
  );
  return out;
}

/** The level's statistics, in dropdown order; none on a single entity. */
export function statisticsFor(level: Level, inspect: boolean): Statistic[] {
  switch (level.kind) {
    case "entity":
      return [];
    case "all-entities":
      return [
        input(
          "Starting residual load",
          "Summed p_set minus available wind and solar (p_nom × p_max_pu), GW",
          (context) => loadVsRenewables(context, "starting"),
        ),
        result(
          "Actual residual load",
          "Summed p_set minus dispatched wind and solar (p), GW",
          (context) => loadVsRenewables(context, "actual"),
        ),
        capacityStatistic(
          "Load vs renewables",
          inspect,
          inspect
            ? "Summed p_set and dispatched wind and solar (p), GW"
            : "Summed p_set and available wind and solar (p_nom × p_max_pu), GW",
          (context) => loadVsRenewables(context, "none"),
        ),
        capacityStatistic(
          "Available generation by carrier",
          inspect,
          `${inspect ? "p_nom_opt" : "p_nom"} × p_max_pu (1 where none is given), stacked by carrier, GW`,
          (context) => availableGeneration(context, true),
        ),
        input("Load duration curve", "Summed p_set, sorted, against hours, GW", loadDuration),
        result("Dispatch by carrier", "Generators’ p, stacked by carrier, GW", (context) =>
          dispatch(context, ["Generator"], true, true),
        ),
        result("Mean bus price", "marginal_price averaged over the AC buses", (context) =>
          meanPrice(context, false, "Mean price"),
        ),
        result(
          "Price duration curve",
          "Mean marginal_price over the AC buses, sorted, against hours",
          (context) => meanPrice(context, true, "Mean price"),
        ),
        result("Hydrogen state of charge", "e summed over the H2 stores, GWh", (context) =>
          stateOfCharge(context, "Store", "%H2%"),
        ),
        result(
          "Optimised capacity by component",
          "p_nom_opt (s_nom_opt for lines, e_nom_opt for stores) per component type, stacked by carrier, GW",
          (context) => optimisedMix(context, "capacity", "ctype"),
        ),
        result(
          "Optimised dispatch by component",
          "Output (positive p; a link’s delivery at its output) summed over the time window, weighted by snapshot hours, per component type, stacked by carrier, GWh. Stores, lines and loads left out",
          (context) => optimisedMix(context, "output", "ctype"),
        ),
      ];
    case "component":
    case "carrier": {
      const { ctype } = level;
      const grouped = level.kind === "component";
      switch (ctype) {
        case "Generator":
          return [
            capacityStatistic(
              "Available generation",
              inspect,
              `${inspect ? "p_nom_opt" : "p_nom"} × p_max_pu${grouped ? ", stacked by carrier" : ""}, GW`,
              (context) => availableGeneration(context, grouped),
            ),
            input(
              "Availability duration curve",
              `Capacity-weighted mean p_max_pu (${inspect ? "p_nom_opt" : "p_nom"}), sorted, against hours`,
              availabilityDuration,
            ),
            ...capacityStatistics(level, ctype, inspect, ["Generator"]),
            result(
              "Dispatch",
              `Hourly generation (p)${grouped ? ", stacked by carrier" : ""}, GW`,
              (context) => dispatch(context, ["Generator"], grouped, true),
            ),
            result(
              "Curtailment",
              "Available (p_nom_opt × p_max_pu) minus dispatched wind and solar, GW",
              curtailment,
            ),
          ];
        case "Load":
          return [
            input("Total load", "Summed p_set, GW", totalLoad),
            input("Load duration curve", "Summed p_set, sorted, against hours, GW", loadDuration),
            input(
              "Peak load by location",
              "The 12 locations with the highest summed p_set in the window, MW",
              async (context) =>
                categoryBars(await loadPeakByLocation(context.scope), "MW", context, "none"),
            ),
          ];
        case "Store":
          return [
            ...capacityStatistics(level, ctype, inspect, ["Store"]),
            result(
              "State of charge",
              `Summed e${grouped ? ", stacked by carrier" : ""}, GWh`,
              (context) => stateOfCharge(context, "Store", null),
            ),
          ];
        case "StorageUnit":
          return [
            ...capacityStatistics(level, ctype, inspect, ["StorageUnit"]),
            result(
              "State of charge",
              `Summed state_of_charge${grouped ? ", stacked by carrier" : ""}, GWh`,
              (context) => stateOfCharge(context, "StorageUnit", null),
            ),
            result("Charge and discharge", "Summed p, positive is discharge, GW", (context) =>
              dispatch(context, ["StorageUnit"], grouped, false),
            ),
          ];
        case "Link":
          return [
            ...capacityStatistics(level, ctype, inspect, ["Link"]),
            result("Flow", `Summed p at bus0${grouped ? ", per carrier" : ""}, GW`, (context) =>
              dispatch(context, ["Link"], grouped, false),
            ),
          ];
        case "Line":
          return [
            capacityStatistic(
              "Largest lines",
              inspect,
              `The 12 largest by ${inspect ? "s_nom_opt" : "s_nom"}, MVA`,
              lineBars,
            ),
            input("Length distribution", "Lines sorted by length, km", (context) =>
              lineRanks(context, "length"),
            ),
            result(
              "Loading duration curve",
              "Lines sorted by mean |p0| ÷ s_nom_opt over the window, %",
              (context) => lineRanks(context, "loading"),
            ),
          ];
        case "GlobalConstraint":
          return [];
        default:
          return capacityStatistics(level, ctype, inspect, [ctype]);
      }
    }
    case "all-locations":
    case "location":
    case "bus": {
      const perBus = level.kind === "all-locations" ? "per bus" : "per bus and component type";
      const by = level.kind === "all-locations" ? "bus" : "bus-ctype";
      const out: Statistic[] = [
        capacityStatistic(
          "Load vs available generation",
          inspect,
          `Summed p_set and available generation (${inspect ? "p_nom_opt" : "p_nom"} × p_max_pu), GW`,
          async (context) => {
            const [axis, load, available] = await Promise.all([
              loadAxis(context.scope),
              loadTotalLoad(context.scope),
              loadAvailable(context.scope, {
                optimised: context.inspect,
                vreOnly: false,
                byCarrier: false,
              }),
            ]);
            const series: SpecSeries[] = [];
            if (load) series.push({ name: "Load", color: NEUTRAL, values: scale(load, GW) });
            const a = available.get("all");
            if (a)
              series.push({ name: "Available generation", color: "#3fbf9f", values: scale(a, GW) });
            return timeSpec(axis, "GW", series);
          },
        ),
        capacityStatistic(
          "Capacity by carrier",
          inspect,
          `Generators’ ${inspect ? "p_nom_opt" : "p_nom"} per carrier, MW`,
          (context) => capacityBars(context, ["Generator"], "carrier", "MW"),
        ),
        result("Dispatch", "Generators’ p, stacked by carrier, GW", (context) =>
          dispatch(context, ["Generator"], true, true),
        ),
        result(
          "Optimised capacity by bus",
          `p_nom_opt (e_nom_opt for stores) ${perBus}, stacked by carrier, GW. Lines left out; links count at bus0`,
          (context) => optimisedMix(context, "capacity", by),
        ),
        result(
          "Optimised dispatch by bus",
          `Output (positive p; a link’s delivery at its output) summed over the time window, weighted by snapshot hours, ${perBus}, stacked by carrier, GWh. Stores, lines and loads left out; links count at bus0`,
          (context) => optimisedMix(context, "output", by),
        ),
      ];
      if (level.kind !== "all-locations")
        out.push(
          result(
            "Bus price",
            level.kind === "bus"
              ? "marginal_price"
              : "marginal_price averaged over the AC buses here",
            (context) => meanPrice(context, false, "Price"),
          ),
        );
      return out;
    }
  }
}
