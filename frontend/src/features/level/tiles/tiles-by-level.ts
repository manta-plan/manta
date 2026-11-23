// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import type { Level } from "../level";
import { capacityUnit, formatMega, formatNumber, formatPercent, plural } from "./format";
import type { Group, TileInputs, TileResults } from "./tile-queries";
import type { TileSpec } from "./tile";

// Which tiles each level shows, and what they say (the handover's "Pages and
// stat tiles"). Capacity-type tiles say "Starting" on Build and "Actual" on
// Inspect, where they count the optimised capacity. A tile from the run
// result shows "—" on Build. Hour-summed figures cover the time window and
// are scaled to a year.

/** A read's state, as the tiles need it. */
export type Source<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: T };

export interface TileContext {
  level: Level;
  /** Inspect with a run result shown: result tiles read it, capacity tiles are "Actual". */
  results: boolean;
  stage: "build" | "inspect";
  period: string;
  /** What the window is called ("Winter", "Mon 7 Jan – Sun 13 Jan", "full span"). */
  windowLabel: string;
  inputs: Source<TileInputs>;
  /** Null where the level has no result tiles or on Build. */
  runResults: Source<TileResults> | null;
  open: (level: Level) => void;
}

type Body = Omit<TileSpec, "key" | "label">;

const DASH = "—";

/** A tile read from the inputs: loading, failed or built. */
function fromInputs(
  ctx: TileContext,
  key: string,
  label: string,
  build: (inputs: TileInputs) => Body,
): TileSpec {
  return fromSource(ctx.inputs, key, label, build);
}

function fromSource<T>(
  source: Source<T>,
  key: string,
  label: string,
  build: (data: T) => Body,
): TileSpec {
  if (source.status === "loading") return { key, label, value: "", loading: true };
  if (source.status === "error") return { key, label, value: DASH, title: source.error };
  return { key, label, ...build(source.data) };
}

/** A run result tile: "—" on Build, else read from the inputs and the result together. */
function fromResults(
  ctx: TileContext,
  key: string,
  label: string,
  build: (inputs: TileInputs, results: TileResults) => Body,
): TileSpec {
  if (!ctx.results || ctx.runResults === null) {
    return {
      key,
      label,
      value: DASH,
      detail: ctx.stage === "build" ? "Available in Inspect" : "Needs a run result",
    };
  }
  const run = ctx.runResults;
  const both: Source<[TileInputs, TileResults]> =
    ctx.inputs.status === "error"
      ? ctx.inputs
      : run.status === "error"
        ? run
        : ctx.inputs.status === "loading" || run.status === "loading"
          ? { status: "loading" }
          : { status: "ready", data: [ctx.inputs.data, run.data] };
  return fromSource(both, key, label, ([inputs, results]) => ({
    result: true,
    ...build(inputs, results),
  }));
}

/** "Starting total capacity" on Build, "Actual total capacity" on Inspect. */
function prefixed(ctx: TileContext, label: string): string {
  return `${ctx.results ? "Actual" : "Starting"} ${label[0].toLowerCase()}${label.slice(1)}`;
}

const sum = (values: (number | null | undefined)[]) =>
  values.reduce<number>((total, value) => total + (value ?? 0), 0);
const groupsOf = (inputs: TileInputs, ctype: string) =>
  inputs.groups.filter((group) => group.ctype === ctype);
const capacityOf = (ctx: TileContext, groups: Group[]) =>
  sum(groups.map((group) => (ctx.results ? group.actual : group.capacity)));
const carrierCount = (groups: Group[]) => new Set(groups.map((group) => group.carrier)).size;
const carrierName = (group: { carrier: string | null; name: string | null }) =>
  group.name ?? group.carrier ?? "No carrier";

/** The window's hours stand for the period's: the factor that turns a window sum into a year's. */
const yearScale = (hours: TileInputs["hours"]) =>
  hours.span_hours > 0 ? hours.period_hours / hours.span_hours : 0;

const typeLevel = (ctype: string): Level => ({ kind: "component", ctype });

function opener(
  ctx: TileContext,
  level: Level,
  name: string,
): Pick<TileSpec, "onOpen" | "openLabel"> {
  return { onOpen: () => ctx.open(level), openLabel: `Open ${name}` };
}

// ——— Tiles shared by several levels ———

function activeEntities(ctx: TileContext): TileSpec {
  return fromInputs(ctx, "active", `Entities active in ${ctx.period}`, ({ counts }) => {
    const parts =
      counts.with_status > 0
        ? [
            `${formatNumber(counts.existing, 0)} existing`,
            `${formatNumber(counts.candidate, 0)} candidate`,
          ]
        : [];
    parts.push(`${formatNumber(counts.not_active, 0)} not active`);
    return { value: formatNumber(counts.active, 0), detail: parts.join(" · ") };
  });
}

function entitiesTile(ctx: TileContext): TileSpec {
  return fromInputs(ctx, "entities", "Entities", ({ counts, groups }) => {
    const parts =
      counts.with_status > 0
        ? [
            `${formatNumber(counts.existing, 0)} existing`,
            `${formatNumber(counts.candidate, 0)} candidate`,
          ]
        : [plural(carrierCount(groups), "carrier")];
    if (counts.not_active > 0) parts.push(`${formatNumber(counts.not_active, 0)} not active`);
    return { value: formatNumber(counts.active, 0), detail: parts.join(" · ") };
  });
}

/** Generation or link capacity of a mixed level; only when it has any. */
function typeCapacity(
  ctx: TileContext,
  ctype: string,
  label: string,
  link: boolean,
): TileSpec | null {
  if (ctx.inputs.status === "ready" && groupsOf(ctx.inputs.data, ctype).length === 0) return null;
  return fromInputs(ctx, `capacity-${ctype}`, prefixed(ctx, label), (inputs) => {
    const groups = groupsOf(inputs, ctype);
    return {
      value: formatMega(capacityOf(ctx, groups), "W"),
      detail: `${plural(carrierCount(groups), "carrier")}${ctx.results ? " · optimised" : ""}`,
      result: ctx.results,
      ...(link ? opener(ctx, typeLevel(ctype), ctype) : {}),
    };
  });
}

function peakLoad(ctx: TileContext, link: boolean): TileSpec | null {
  if (ctx.inputs.status === "ready" && !(ctx.inputs.data.load && ctx.inputs.data.load.loads > 0))
    return null;
  return fromInputs(ctx, "peak-load", "Peak load", ({ load }) => ({
    value: formatMega(load?.peak, "W"),
    detail: `mean ${formatMega(load?.mean, "W")}, ${ctx.windowLabel}`,
    ...(link ? opener(ctx, typeLevel("Load"), "Load") : {}),
  }));
}

function storageVolume(ctx: TileContext, link: boolean): TileSpec | null {
  if (
    ctx.inputs.status === "ready" &&
    !(ctx.inputs.data.volumes && ctx.inputs.data.volumes.stores > 0)
  )
    return null;
  return fromInputs(
    ctx,
    "storage-volume",
    prefixed(ctx, "Storage volume"),
    ({ volumes, groups }) => {
      const storage = groups.filter(
        (group) => group.ctype === "Store" || group.ctype === "StorageUnit",
      );
      return {
        value: formatMega(ctx.results ? volumes?.storage_actual : volumes?.storage, "Wh"),
        detail: `${plural(carrierCount(storage), "carrier")}${ctx.results ? " · optimised" : ""}`,
        result: ctx.results,
        ...(link ? opener(ctx, typeLevel("Store"), "Store") : {}),
      };
    },
  );
}

function transmissionVolume(ctx: TileContext, link: boolean): TileSpec | null {
  if (
    ctx.inputs.status === "ready" &&
    !(ctx.inputs.data.volumes && ctx.inputs.data.volumes.lines > 0)
  )
    return null;
  return fromInputs(
    ctx,
    "transmission-volume",
    prefixed(ctx, "Transmission volume"),
    ({ volumes }) => {
      const lines = volumes?.lines ?? 0;
      const missing = volumes?.lines_without_length ?? 0;
      return {
        value: formatMega(
          ctx.results ? volumes?.transmission_actual : volumes?.transmission,
          "W·km",
        ),
        detail: `${plural(lines, "line")} · s_nom × length${missing > 0 ? ` · ${formatNumber(missing, 0)} without length` : ""}`,
        result: ctx.results,
        ...(link ? opener(ctx, typeLevel("Line"), "Line") : {}),
      };
    },
  );
}

/** Total capacity: existing grey and new blue on Inspect. */
function totalCapacity(ctx: TileContext, ctype: string): TileSpec {
  const unit = capacityUnit(
    ctype === "Store" ? "e_nom" : ctype === "Line" || ctype === "Transformer" ? "s_nom" : "p_nom",
  );
  return fromInputs(ctx, "total-capacity", prefixed(ctx, "Total capacity"), ({ groups }) => {
    const existing = sum(groups.map((group) => group.capacity));
    if (!ctx.results)
      return { value: formatMega(existing, unit), detail: "Existing · new build shown in Inspect" };
    const added = sum(groups.map((group) => group.new_build));
    return {
      value: formatMega(sum(groups.map((group) => group.actual)), unit),
      detail: `${formatMega(existing, unit)} existing + ${formatMega(added, unit)} new`,
      result: true,
      bar: { existing, added },
    };
  });
}

/** Largest carrier when the level has several, else its largest entity. */
function largest(ctx: TileContext, ctype: string, noun: string): TileSpec {
  const unit = capacityUnit(
    ctype === "Store" ? "e_nom" : ctype === "Line" || ctype === "Transformer" ? "s_nom" : "p_nom",
  );
  const several =
    ctx.level.kind === "component" &&
    ctx.inputs.status === "ready" &&
    carrierCount(ctx.inputs.data.groups) > 1;
  const label = prefixed(ctx, several ? "Largest carrier" : `Largest ${noun}`);
  return fromInputs(ctx, "largest", label, ({ groups }) => {
    const total = capacityOf(ctx, groups);
    const share = (value: number) =>
      `${formatMega(value, unit)} · ${formatNumber(total > 0 ? (value / total) * 100 : 0, 0)}% of the total`;
    if (!(total > 0))
      return {
        value: DASH,
        detail: ctx.results ? "No capacity" : "No existing capacity",
        result: ctx.results,
      };
    if (several) {
      const top = [...groups].sort((a, b) => capacityOf(ctx, [b]) - capacityOf(ctx, [a]))[0];
      return {
        value: carrierName(top),
        dot: top.color,
        small: true,
        detail: share(capacityOf(ctx, [top])),
        result: ctx.results,
        ...(top.carrier !== null
          ? opener(ctx, { kind: "carrier", ctype, carrier: top.carrier }, carrierName(top))
          : {}),
      };
    }
    const best = groups
      .map((group) =>
        ctx.results
          ? { entity: group.largest_actual, capacity: group.largest_actual_capacity }
          : { entity: group.largest, capacity: group.largest_capacity },
      )
      .filter(
        (item): item is { entity: string; capacity: number } =>
          item.entity !== null && item.capacity !== null,
      )
      .sort((a, b) => b.capacity - a.capacity)[0];
    if (!best) return { value: DASH };
    return {
      value: best.entity,
      small: true,
      title: best.entity,
      detail: share(best.capacity),
      result: ctx.results,
      ...opener(ctx, { kind: "entity", entity: best.entity }, best.entity),
    };
  });
}

const flowOf = (results: TileResults, ctype: string) =>
  results.flows.find((flow) => flow.ctype === ctype) ?? null;

// ——— Levels ———

function overviewTiles(ctx: TileContext): (TileSpec | null)[] {
  const link = ctx.level.kind === "all-entities";
  return [
    activeEntities(ctx),
    typeCapacity(ctx, "Generator", "Generation capacity", link),
    typeCapacity(ctx, "Link", "Link capacity", link),
    peakLoad(ctx, link),
    storageVolume(ctx, link),
    transmissionVolume(ctx, link),
  ];
}

function locationsTiles(ctx: TileContext): (TileSpec | null)[] {
  return [
    fromInputs(ctx, "locations", "Locations", ({ locations }) => ({
      value: formatNumber(locations?.count, 0),
      detail: locations?.regions
        ? `substations in ${formatNumber(locations.regions.zones, 0)} ${locations.regions.level} regions`
        : "substations",
    })),
    fromInputs(ctx, "buses", "Buses", ({ locations }) => {
      const buses = locations?.buses ?? [];
      const detail = buses
        .map((item) => `${item.carrier ?? "no carrier"} ${formatNumber(item.buses, 0)}`)
        .join(" · ");
      return {
        value: formatNumber(sum(buses.map((item) => item.buses)), 0),
        detail,
        title: detail,
      };
    }),
    peakLoad(ctx, false),
    storageVolume(ctx, false),
    transmissionVolume(ctx, false),
  ];
}

function generatorTiles(ctx: TileContext): TileSpec[] {
  return [
    entitiesTile(ctx),
    totalCapacity(ctx, "Generator"),
    ctx.results
      ? fromResults(
          ctx,
          "capacity-factor",
          prefixed(ctx, "Mean capacity factor"),
          (inputs, results) => {
            const capacityHours =
              sum(inputs.groups.map((group) => group.actual)) * results.hours.span_hours;
            const generation = flowOf(results, "Generator")?.net ?? null;
            return {
              value: formatPercent(
                generation !== null && capacityHours > 0 ? generation / capacityHours : null,
              ),
              detail: `Generation ÷ (p_nom_opt × hours), ${ctx.windowLabel}`,
            };
          },
        )
      : fromInputs(
          ctx,
          "capacity-factor",
          prefixed(ctx, "Mean capacity factor"),
          ({ capacityFactor }) => ({
            value: formatPercent(capacityFactor?.estimate),
            detail: `Estimated · p_max_pu, capacity-weighted, ${ctx.windowLabel}`,
            title: capacityFactor
              ? `${formatNumber(capacityFactor.with_profile, 0)} of ${formatNumber(capacityFactor.generators, 0)} generators have p_max_pu; the rest count as 1`
              : undefined,
          }),
        ),
    largest(ctx, "Generator", "generator"),
    fromResults(ctx, "curtailment", "Curtailment", (_inputs, results) => {
      const g = results.generators;
      if (!g || !(g.available && g.available > 0))
        return { value: DASH, detail: "No variable renewables here" };
      return {
        value: formatPercent((g.curtailed ?? 0) / g.available),
        detail: `${formatMega((g.curtailed ?? 0) * yearScale(results.hours), "Wh")} a year`,
      };
    }),
    fromResults(ctx, "market-value", "Market value", (_inputs, results) => {
      const g = results.generators;
      return {
        value: g?.market_value == null ? DASH : `${formatNumber(g.market_value, 1)} €/MWh`,
        detail:
          g?.mean_price == null
            ? "Generation-weighted bus price"
            : `Generation-weighted · mean price ${formatNumber(g.mean_price, 1)} €/MWh`,
      };
    }),
  ];
}

function loadTiles(ctx: TileContext): TileSpec[] {
  return [
    fromInputs(ctx, "annual-demand", "Annual demand", ({ load, hours }) => ({
      value: formatMega(load?.mean == null ? null : load.mean * hours.period_hours, "Wh"),
      detail: `Estimated · mean over ${ctx.windowLabel} × ${formatNumber(hours.period_hours, 0)} h`,
    })),
    fromInputs(ctx, "peak-load", "Peak load", ({ load }) => ({
      value: formatMega(load?.peak, "W"),
      detail: `Peak of the summed p_set, ${ctx.windowLabel}`,
    })),
    fromInputs(ctx, "peak-to-mean", "Peak-to-mean ratio", ({ load }) => ({
      value: load?.peak != null && load.mean ? formatNumber(load.peak / load.mean, 2) : DASH,
      detail: `Mean ${formatMega(load?.mean, "W")}`,
    })),
    fromInputs(ctx, "largest", "Largest load", ({ load, hours }) => {
      if (!load?.largest) return { value: DASH };
      const share = load.mean
        ? ` · ${formatNumber(((load.largest_mean ?? 0) / load.mean) * 100, 0)}% of the total`
        : "";
      return {
        value: load.largest,
        small: true,
        title: load.largest,
        detail: `${formatMega((load.largest_mean ?? 0) * hours.period_hours, "Wh")} a year${share}`,
        ...opener(ctx, { kind: "entity", entity: load.largest }, load.largest),
      };
    }),
  ];
}

function storageTiles(ctx: TileContext, ctype: "Store" | "StorageUnit"): (TileSpec | null)[] {
  const unit = ctype === "StorageUnit";
  return [
    entitiesTile(ctx),
    totalCapacity(ctx, ctype),
    largest(ctx, ctype, unit ? "storage unit" : "store"),
    unit ? storageVolume(ctx, false) : null,
    unit
      ? fromInputs(ctx, "efficiency", "Efficiency", ({ volumes }) => ({
          value: formatPercent(volumes?.unit_efficiency),
          detail:
            volumes?.unit_efficiency == null
              ? "Not in the input data"
              : "Round trip: efficiency_store × efficiency_dispatch",
        }))
      : fromInputs(ctx, "efficiency", "Round-trip efficiency", ({ storeEfficiency }) => {
          const trip =
            storeEfficiency?.charge != null && storeEfficiency.discharge != null
              ? storeEfficiency.charge * storeEfficiency.discharge
              : null;
          return {
            value: formatPercent(trip),
            detail:
              trip === null
                ? "No charging and discharging links"
                : `Estimated · charging ${formatPercent(storeEfficiency?.charge)} × discharging ${formatPercent(storeEfficiency?.discharge)} links`,
          };
        }),
    fromResults(ctx, "stored-energy", "Stored energy", (_inputs, results) => ({
      value: formatMega((flowOf(results, ctype)?.in ?? 0) * yearScale(results.hours), "Wh"),
      detail: "Energy charged a year",
    })),
    fromResults(ctx, "capacity-factor", "Capacity factor", (inputs, results) => {
      const capacity = sum(inputs.groups.map((group) => group.actual));
      const hours = results.hours.span_hours;
      if (unit) {
        const out = flowOf(results, ctype)?.out ?? null;
        return {
          value: formatPercent(
            out !== null && capacity * hours > 0 ? out / (capacity * hours) : null,
          ),
          detail: "Discharge ÷ (p_nom_opt × hours)",
        };
      }
      const energy = results.stores?.energy ?? null;
      return {
        value: formatPercent(
          energy !== null && capacity > 0 && hours > 0 ? energy / hours / capacity : null,
        ),
        detail: "Mean state of charge ÷ e_nom_opt",
      };
    }),
  ];
}

/** Mean |p0| ÷ capacity over the window, for links and lines. */
function flowFactor(ctx: TileContext, ctype: string, detail: string): TileSpec {
  return fromResults(ctx, "capacity-factor", "Capacity factor", (inputs, results) => {
    const capacityHours =
      sum(inputs.groups.map((group) => group.actual)) * results.hours.span_hours;
    const flow = flowOf(results, ctype)?.both_ways ?? null;
    return {
      value: formatPercent(flow !== null && capacityHours > 0 ? flow / capacityHours : null),
      detail,
    };
  });
}

function linkTiles(ctx: TileContext): TileSpec[] {
  return [
    entitiesTile(ctx),
    totalCapacity(ctx, "Link"),
    largest(ctx, "Link", "link"),
    flowFactor(ctx, "Link", "Throughput ÷ (p_nom_opt × hours)"),
  ];
}

function lineTiles(ctx: TileContext): (TileSpec | null)[] {
  return [
    transmissionVolume(ctx, false),
    totalCapacity(ctx, "Line"),
    largest(ctx, "Line", "line"),
    flowFactor(ctx, "Line", "Mean loading: |p0| ÷ s_nom_opt"),
    fromInputs(ctx, "voltages", "Voltage levels", ({ volumes }) => {
      const kv = volumes?.kv ?? [];
      if (kv.length === 0) return { value: DASH, detail: "v_nom not in the data" };
      const value = kv.map((v) => `${formatNumber(v, 0)} kV`).join(", ");
      return { value, small: true, title: value, detail: plural(kv.length, "level") };
    }),
  ];
}

function otherTypeTiles(ctx: TileContext, ctype: string): (TileSpec | null)[] {
  const hasCapacity = !(
    ctx.inputs.status === "ready" &&
    ctx.inputs.data.groups.every((group) => group.capacity === null)
  );
  return [entitiesTile(ctx), hasCapacity ? totalCapacity(ctx, ctype) : null];
}

function typeTiles(ctx: TileContext, ctype: string): (TileSpec | null)[] {
  switch (ctype) {
    case "Generator":
      return generatorTiles(ctx);
    case "Load":
      return loadTiles(ctx);
    case "Store":
    case "StorageUnit":
      return storageTiles(ctx, ctype);
    case "Link":
      return linkTiles(ctx);
    case "Line":
      return lineTiles(ctx);
    default:
      return otherTypeTiles(ctx, ctype);
  }
}

function entityTiles(ctx: TileContext): (TileSpec | null)[] {
  const entity = ctx.inputs.status === "ready" ? ctx.inputs.data.entity : null;
  if (ctx.inputs.status === "ready" && entity === null)
    return [
      { key: "missing", label: "Entity", value: DASH, detail: `Not active in ${ctx.period}` },
    ];
  const ctype = entity?.ctype ?? null;
  const unit = capacityUnit(entity?.cap_attribute ?? null);
  const tiles: (TileSpec | null)[] = [
    fromInputs(ctx, "component", "Component", ({ entity: e }) => ({
      value: e?.ctype ?? DASH,
      small: true,
      dot: e?.color ?? null,
      detail: e ? carrierName(e) : undefined,
      ...(e && e.carrier !== null
        ? opener(ctx, { kind: "carrier", ctype: e.ctype, carrier: e.carrier }, carrierName(e))
        : {}),
    })),
    fromInputs(ctx, "location", "Location", ({ entity: e }) => {
      if (!e?.location) return { value: DASH, small: true, detail: "No location" };
      const value =
        e.location1 && e.location1 !== e.location ? `${e.location} → ${e.location1}` : e.location;
      return {
        value,
        small: true,
        title: value,
        detail: e.bus ? `bus ${e.bus}` : undefined,
        ...opener(ctx, { kind: "location", location: e.location }, e.location),
      };
    }),
    ctype === "Load"
      ? fromInputs(ctx, "peak-load", "Peak load", ({ load }) => ({
          value: formatMega(load?.peak, "W"),
          detail: `peak of p_set, ${ctx.windowLabel}`,
        }))
      : fromInputs(ctx, "existing-capacity", "Existing capacity", ({ entity: e }) => ({
          value: e?.capacity == null ? DASH : formatMega(e.capacity, unit),
          detail: `${e?.cap_attribute ?? "no capacity"} · ${e?.status ?? "—"}`,
        })),
  ];
  if (ctype === "StorageUnit") {
    tiles.push(
      fromInputs(ctx, "storage-volume", "Storage volume", ({ entity: e }) => ({
        value: formatMega((e?.capacity ?? 0) * (e?.max_hours ?? 1), "Wh"),
        detail: `${formatMega(e?.capacity, "W")} × ${formatNumber(e?.max_hours ?? 1)} h`,
      })),
    );
  }
  if (ctype === "Line") {
    tiles.push(
      fromInputs(ctx, "transmission-volume", "Transmission volume", ({ entity: e }) => ({
        value: e?.length == null ? DASH : formatMega((e.capacity ?? 0) * e.length, "W·km"),
        detail:
          e?.length == null
            ? "length not in the data"
            : `${formatMega(e.capacity, "VA")} × ${formatNumber(e.length)} km`,
      })),
    );
  }
  if (ctx.results && ctype !== null && ctype !== "Load" && entity?.cap_attribute) {
    tiles.push(
      fromResults(ctx, "optimised", `Optimised in ${ctx.period}`, ({ entity: e }) => ({
        value: e?.capacity_opt == null ? DASH : formatMega(e.capacity_opt, unit),
        detail: `${e?.cap_attribute}_opt`,
      })),
    );
    const generator = ctype === "Generator";
    tiles.push(
      fromResults(
        ctx,
        "energy",
        `${generator ? "Generation" : "Throughput"} in ${ctx.period}`,
        ({ entity: e }, results) => {
          const flow = flowOf(results, ctype);
          const energy =
            flow === null
              ? null
              : generator
                ? flow.net
                : ctype === "Store" || ctype === "StorageUnit"
                  ? flow.out
                  : flow.both_ways;
          const capacity = e?.capacity_opt ?? e?.capacity ?? 0;
          const hours = results.hours.span_hours;
          const factor =
            energy !== null && capacity > 0 && hours > 0 && ctype !== "Store"
              ? energy / (capacity * hours)
              : null;
          return {
            value: formatMega(energy === null ? null : energy * yearScale(results.hours), "Wh"),
            detail:
              factor === null ? "a year" : `a year · capacity factor ${formatPercent(factor)}`,
          };
        },
      ),
    );
  }
  return tiles;
}

/** The level's tiles, in order. */
export function levelTiles(ctx: TileContext): TileSpec[] {
  let tiles: (TileSpec | null)[];
  switch (ctx.level.kind) {
    case "all-entities":
    case "location":
    case "bus":
      tiles = overviewTiles(ctx);
      break;
    case "all-locations":
      tiles = locationsTiles(ctx);
      break;
    case "component":
    case "carrier":
      tiles = typeTiles(ctx, ctx.level.ctype);
      break;
    case "entity":
      tiles = entityTiles(ctx);
      break;
  }
  return tiles.filter((tile): tile is TileSpec => tile !== null);
}
