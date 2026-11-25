import type { Manifest } from "../../project/lib/record-server/types";
import type { LevelQueryScope } from "../level-sql";
import type { PickedSeries } from "../level-store";
import {
  attributeDim,
  loadAttributeAggregate,
  loadAttributeDistribution,
  loadAttributeEach,
  loadAxis,
  type AttributeDim,
  type AttributeOptionRow,
  type PickQuery,
} from "./chart-sql";
import {
  ACCENT,
  isPerUnit,
  isRate,
  LINE_THRESHOLD,
  PALETTE,
  sumUnit,
  type ChartSpec,
} from "./spec";

// Attributes mode: one series attribute of the level's members ("Generator ·
// p_max_pu"), aggregated (Sum, Mean, All, Each) or as the series picked in
// the table.

/** Attributes a solve writes: read from a run result, greyed in Build. */
export const RESULT_ATTRIBUTES = new Set([
  "p",
  "p0",
  "p1",
  "q",
  "e",
  "state_of_charge",
  "p_dispatch",
  "p_store",
  "p_internal",
  "spill",
  "marginal_price",
  "v_ang",
  "v_mag_pu",
  "mu",
  "mu_upper",
  "mu_lower",
  "status",
]);

/** The result series each type has, listed (greyed) in Build where the type is at the level. */
const RESULT_SERIES: Record<string, string[]> = {
  Generator: ["p"],
  Load: ["p"],
  Link: ["p"],
  Line: ["p"],
  Transformer: ["p"],
  Store: ["e", "p"],
  StorageUnit: ["p", "state_of_charge"],
};

export interface AttributeOption {
  /** "Generator · p_max_pu": what the store keeps. */
  id: string;
  ctype: string;
  attribute: string;
  unit: string | null;
  dim: AttributeDim;
  /** Subjects storing it at the level. */
  n: number;
  result: boolean;
  /** Readable in the catalog shown (a result in Build isn't). */
  available: boolean;
}

export const optionId = (ctype: string, attribute: string) => `${ctype} · ${attribute}`;

/** The dropdown's attributes: those read at the level, then results the level would have in a run result, greyed. */
export function attributeOptions(
  rows: AttributeOptionRow[],
  ctypes: string[],
  withBuses: boolean,
  manifest: Manifest | undefined,
  inspect: boolean,
): AttributeOption[] {
  const option = (
    ctype: string,
    attribute: string,
    n: number,
    available: boolean,
  ): AttributeOption => {
    const spec = manifest?.attributes[attribute];
    return {
      id: optionId(ctype, attribute),
      ctype,
      attribute,
      unit: spec?.unit ?? null,
      dim: ctype === "Bus" ? "bus" : attributeDim(spec?.dims),
      n,
      result: RESULT_ATTRIBUTES.has(attribute),
      available,
    };
  };
  const out = rows.map((row) =>
    option(row.ctype, row.attribute, row.n, inspect || !RESULT_ATTRIBUTES.has(row.attribute)),
  );
  const has = new Set(out.map((item) => item.id));
  const missing: AttributeOption[] = [];
  for (const ctype of ctypes)
    for (const attribute of RESULT_SERIES[ctype] ?? [])
      if (!has.has(optionId(ctype, attribute))) missing.push(option(ctype, attribute, 0, false));
  if (withBuses && !has.has(optionId("Bus", "marginal_price")))
    missing.push(option("Bus", "marginal_price", 0, false));
  // Inputs first, then results; each by type.
  return [...out, ...missing].sort(
    (a, b) =>
      Number(a.result) - Number(b.result) ||
      a.ctype.localeCompare(b.ctype) ||
      a.attribute.localeCompare(b.attribute),
  );
}

export type Aggregation = "sum" | "mean" | "all" | "each";

/** p.u. attributes and prices aren't summed. */
export function aggregationsFor(unit: string | null): Aggregation[] {
  return isPerUnit(unit) || isRate(unit) ? ["mean", "all", "each"] : ["sum", "mean", "all", "each"];
}

export function aggregationLabel(aggregation: Aggregation, unit: string | null): string {
  switch (aggregation) {
    case "sum":
      return "Sum";
    case "mean":
      return isPerUnit(unit) ? "Mean, capacity-weighted" : "Mean";
    case "all":
      return "All";
    case "each":
      return `Each (largest ${LINE_THRESHOLD})`;
  }
}

/** What the chart's caption says after "<Component · attr> [unit] · ". */
export function aggregationCaption(option: AttributeOption, aggregation: Aggregation): string {
  const { n } = option;
  const things =
    option.ctype === "Bus" ? (n === 1 ? "bus" : "buses") : n === 1 ? "entity" : "entities";
  switch (aggregation) {
    case "sum":
      return `sum over ${n.toLocaleString()} ${things}`;
    case "mean":
      return `${isPerUnit(option.unit) ? "capacity-weighted mean" : "mean"} over ${n.toLocaleString()} ${things}`;
    case "all":
      return n > LINE_THRESHOLD
        ? `all ${n.toLocaleString()} ${things}: median line, P25–P75 band (darker) and min–max band (lighter)`
        : `all ${n.toLocaleString()} ${things}`;
    case "each":
      return `${Math.min(LINE_THRESHOLD, n)} of ${n.toLocaleString()} shown`;
  }
}

/** The chart of an attribute over the level, aggregated. */
export async function loadAttributeChart(
  scope: LevelQueryScope,
  option: AttributeOption,
  aggregation: Aggregation,
  inspect: boolean,
): Promise<ChartSpec | null> {
  const query = {
    ctype: option.ctype,
    attribute: option.attribute,
    dim: option.dim,
    optimised: inspect,
  };
  const unit = option.unit ?? "";
  const axisPromise = loadAxis(scope);
  if (aggregation === "sum" || aggregation === "mean") {
    const how = aggregation === "sum" ? "sum" : isPerUnit(option.unit) ? "weighted" : "mean";
    const [axis, lists] = await Promise.all([
      axisPromise,
      loadAttributeAggregate(scope, query, how),
    ]);
    const values = lists.get("value");
    if (!values) return null;
    const shown = aggregation === "sum" ? sumUnit(option.unit) : { unit, scale: 1 };
    return {
      kind: "time",
      unit: shown.unit,
      times: axis.times,
      series: [
        {
          name: aggregation === "sum" ? "Sum" : "Mean",
          color: ACCENT,
          values: values.map((value) => (value === null ? null : value * shown.scale)),
        },
      ],
    };
  }
  if (aggregation === "all" && option.n > LINE_THRESHOLD) {
    const [axis, lists] = await Promise.all([axisPromise, loadAttributeDistribution(scope, query)]);
    const get = (name: string) => (lists.get(name) ?? []).map((value) => value ?? 0);
    if (!lists.has("median")) return null;
    return {
      kind: "time",
      unit,
      times: axis.times,
      series: [],
      distribution: {
        count: option.n,
        min: get("min"),
        p25: get("p25"),
        median: get("median"),
        p75: get("p75"),
        max: get("max"),
      },
    };
  }
  const [axis, each] = await Promise.all([
    axisPromise,
    loadAttributeEach(scope, query, LINE_THRESHOLD),
  ]);
  if (each.length === 0) return null;
  return {
    kind: "time",
    unit,
    times: axis.times,
    series: each.map((item, index) => ({
      name: item.key,
      color: PALETTE[index % PALETTE.length],
      values: item.values,
    })),
  };
}

// ------------------------------------------------------------ Picked series

export interface PickInfo {
  pick: PickedSeries;
  query: PickQuery;
  unit: string;
  result: boolean;
  /** "<attribute> · <owner>". */
  label: string;
  color: string;
}

export function pickInfos(picks: PickedSeries[], manifest: Manifest | undefined): PickInfo[] {
  return picks.map((pick, index) => {
    const spec = manifest?.attributes[pick.attribute];
    const dim: AttributeDim = pick.ctype === "Bus" ? "bus" : attributeDim(spec?.dims);
    return {
      pick,
      query: {
        attribute: pick.attribute,
        dim,
        subject: pick.entity,
        bus: dim === "connection" ? pick.bus : null,
      },
      unit: pick.unit ?? spec?.unit ?? "",
      result: RESULT_ATTRIBUTES.has(pick.attribute),
      label: `${pick.attribute} · ${pick.entity}`,
      color: PALETTE[index % PALETTE.length],
    };
  });
}
