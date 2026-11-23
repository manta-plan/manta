// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import type { ReactNode } from "react";
import { componentKind } from "../component-page";
import { entityLabel, formatValue } from "../../project/lib/record-format";
import { changeKey, defaultFor } from "../../project/lib/record-server/queries";
import type { Manifest, ScenarioChangeValue } from "../../project/lib/record-server/types";
import type { Level } from "../level";
import type { PickedSeries } from "../level-store";
import { CarrierCell, CopyId, Dot, GeoButton, LinkButton, SeriesChip, StatusCell } from "./cells";
import { formatCell } from "./format";
import { SERIES_VALUE, type TableColumn } from "./columns";
import type { GeometryKind, LocationRow, MemberRow, MemberValue, MixedRow } from "./table-queries";

// The columns of each kind of level (handover, "Entity table"):
// - mixed levels (All entities, a location, a bus): one row per entity of
//   any type, with its capacity and profile;
// - a component or carrier: one column per attribute;
// - All locations: one row per location.

export interface ColumnContext {
  level: Level;
  inspect: boolean;
  /** Hours the window stands for, for series chips. */
  hours: number;
  period: string;
  carrier: (carrier: string | null) => { name: string; color: string | null };
  openLevel: (level: Level) => void;
  manifest: Manifest;
  /** Values the shown scenario changes against its parent (Build only), by changeKey. */
  changes: Map<string, ScenarioChangeValue> | null;
  /** The scenario's parent's name, for a changed value's tooltip. */
  parentLabel: string;
  /** Result attributes (Inspect). */
  results: Set<string>;
  regionOf: (location: string) => string | null;
}

/** What every entity row has. */
interface EntityRow {
  entity: string;
  ctype: string;
  carrier: string | null;
  bus: string | null;
  bus1: string | null;
  location: string | null;
  location1: string | null;
  status: string | null;
  geometry: GeometryKind;
}

const unitOf = (manifest: Manifest, attribute: string | null) =>
  attribute ? (manifest.attributes[attribute]?.unit ?? null) : null;
const withUnit = (name: string, unit: string | null) => (unit ? `${name} [${unit}]` : name);
const CHANGED = "bg-accent-600/15 text-accent-200";

function changedTitle(
  ctx: ColumnContext,
  change: ScenarioChangeValue | undefined,
  attribute: string,
) {
  if (!change) return undefined;
  const was =
    change.seriesRows > 0
      ? `${change.seriesRows.toLocaleString()} values changed`
      : formatValue(change.before, ctx.manifest.attributes[attribute]);
  return `Changed by this scenario; ${ctx.parentLabel} has ${was}`;
}

/** Entity, Component, Carrier, Status, Location, Bus (or Connection) and Geolocated. */
function entityColumns<R extends EntityRow>(
  ctx: ColumnContext,
  rows: readonly R[],
  { component }: { component: boolean },
): TableColumn<R>[] {
  const { level } = ctx;
  const columns: TableColumn<R>[] = [];
  const at =
    level.kind === "location" ? level.location : level.kind === "bus" ? level.location : null;
  columns.push({
    key: "entity",
    header: "Entity",
    kind: "text",
    maxChars: 48,
    value: (row) => row.entity,
    render: (row) => (
      <span className="text-surface-100 flex min-w-0 items-center gap-1 font-mono text-[11.5px]">
        <LinkButton
          onClick={() => ctx.openLevel({ kind: "entity", entity: row.entity })}
          title={row.entity}
        >
          {entityLabel(row.entity, at)}
        </LinkButton>
        <CopyId text={row.entity} />
      </span>
    ),
  });
  if (component)
    columns.push({
      key: "ctype",
      header: "Component",
      kind: "text",
      value: (row) => row.ctype,
      render: (row) => (
        <LinkButton onClick={() => ctx.openLevel({ kind: "component", ctype: row.ctype })}>
          {row.ctype}
        </LinkButton>
      ),
    });
  if (level.kind !== "carrier")
    columns.push({
      key: "carrier",
      header: "Carrier",
      kind: "text",
      value: (row) => row.carrier,
      label: (value) => ctx.carrier(value).name,
      render: (row) => {
        const info = ctx.carrier(row.carrier);
        return (
          <CarrierCell
            carrier={row.carrier}
            name={info.name}
            color={info.color}
            onOpen={
              row.carrier
                ? () => ctx.openLevel({ kind: "carrier", ctype: row.ctype, carrier: row.carrier! })
                : undefined
            }
          />
        );
      },
    });
  if (rows.some((row) => row.status))
    columns.push({
      key: "status",
      header: "Status",
      kind: "text",
      value: (row) => row.status,
      render: (row) => <StatusCell status={row.status} />,
    });
  const locationLink = (location: string) => (
    <LinkButton
      key={location}
      mono
      title={location}
      onClick={() => ctx.openLevel({ kind: "location", location })}
    >
      {location}
    </LinkButton>
  );
  const busLink = (bus: string, location: string | null) => (
    <LinkButton
      key={bus}
      mono
      title={bus}
      onClick={() => ctx.openLevel({ kind: "bus", bus, location })}
    >
      {bus}
    </LinkButton>
  );
  const joined = (parts: ReactNode[], separator: string) => (
    <span className="flex min-w-0 items-center gap-1">
      {parts.filter(Boolean).map((part, index) => (
        <span key={index} className="flex min-w-0 items-center gap-1">
          {index > 0 && <span className="text-surface-500">{separator}</span>}
          {part}
        </span>
      ))}
    </span>
  );
  if (level.kind !== "location" && level.kind !== "bus")
    columns.push({
      key: "location",
      header: "Location",
      kind: "text",
      value: (row) =>
        [row.location, row.location1 !== row.location ? row.location1 : null]
          .filter(Boolean)
          .join(" – ") || null,
      render: (row) =>
        joined(
          [
            row.location ? locationLink(row.location) : null,
            row.location1 && row.location1 !== row.location ? locationLink(row.location1) : null,
          ],
          "–",
        ),
    });
  if (level.kind === "bus") {
    const connection = (row: R): { word: string; bus: string | null; location: string | null } =>
      row.bus === level.bus && row.bus1
        ? { word: "to", bus: row.bus1, location: row.location1 }
        : row.bus1 === level.bus && row.bus
          ? { word: "from", bus: row.bus, location: row.location }
          : { word: "attached", bus: null, location: null };
    columns.push({
      key: "connection",
      header: "Connection",
      kind: "text",
      value: (row) => {
        const found = connection(row);
        return found.bus ? `${found.word} ${found.bus}` : found.word;
      },
      render: (row) => {
        const found = connection(row);
        return (
          <span className="flex min-w-0 items-center gap-1">
            <span className="text-surface-400">{found.word}</span>
            {found.bus && busLink(found.bus, found.location)}
          </span>
        );
      },
    });
  } else
    columns.push({
      key: "bus",
      header: "Bus",
      kind: "text",
      value: (row) => [row.bus, row.bus1].filter(Boolean).join(" → ") || null,
      render: (row) =>
        joined(
          [
            row.bus ? busLink(row.bus, row.location) : null,
            row.bus1 ? busLink(row.bus1, row.location1) : null,
          ],
          "→",
        ),
    });
  columns.push({
    key: "geolocated",
    header: "Geolocated",
    kind: "text",
    value: (row) => (row.geometry === "point" ? "site" : row.geometry === "route" ? "route" : null),
    label: (value) => value,
    render: (row) => <GeoButton entity={row.entity} kind={row.geometry} />,
  });
  return columns;
}

// ------------------------------------------------------------ Mixed levels

export function mixedColumns(
  ctx: ColumnContext,
  rows: readonly MixedRow[],
): TableColumn<MixedRow>[] {
  const columns = entityColumns(ctx, rows, { component: true });
  const capacityChange = (row: MixedRow) =>
    ctx.changes && row.cap_attribute
      ? ctx.changes.get(changeKey(row.cap_attribute, "entity", row.entity, null))
      : undefined;
  columns.push({
    key: "capacity",
    header: "Capacity",
    description: "p_nom, s_nom or e_nom; a load’s peak p_set in the time window",
    kind: "number",
    value: (row) => (row.ctype === "Load" ? row.peak : row.capacity),
    render: (row) => (
      <span className="tabular-nums">
        {formatCell(row.ctype === "Load" ? row.peak : row.capacity)}{" "}
        <small className="text-surface-400">
          {row.ctype === "Load" ? "MW peak" : (unitOf(ctx.manifest, row.cap_attribute) ?? "")}
        </small>
      </span>
    ),
    cellClass: (row) => (capacityChange(row) ? CHANGED : undefined),
    cellTitle: (row) =>
      row.cap_attribute ? changedTitle(ctx, capacityChange(row), row.cap_attribute) : undefined,
  });
  const profileSeries = (row: MixedRow): PickedSeries | null =>
    row.profile && row.profile_rows > 0
      ? {
          entity: row.entity,
          ctype: row.ctype,
          attribute: row.profile,
          bus: null,
          unit: unitOf(ctx.manifest, row.profile),
        }
      : null;
  columns.push({
    key: "profile",
    header: "p_max_pu / p_set",
    description:
      "A generator’s availability (p_max_pu) or a load’s demand (p_set): a series or a constant",
    kind: "series",
    value: (row) => (profileSeries(row) ? SERIES_VALUE : row.profile_constant),
    series: profileSeries,
    render: (row) => {
      const series = profileSeries(row);
      if (series) return <SeriesChip series={series} hours={ctx.hours} />;
      return row.profile_constant === null ? (
        <span className="text-surface-500">—</span>
      ) : (
        formatValue(row.profile_constant, {
          dtype: ctx.manifest.attributes[row.profile ?? ""]?.dtype,
          unit: null,
        })
      );
    },
  });
  if (ctx.inspect) {
    columns.push({
      key: "optimised",
      header: "Optimised",
      description: "p_nom_opt, s_nom_opt or e_nom_opt from the run result",
      kind: "number",
      value: (row) => row.capacity_opt,
      render: (row) => formatCell(row.capacity_opt),
    });
    const dispatch = (row: MixedRow): PickedSeries | null =>
      row.dispatch_rows > 0 && row.bus
        ? { entity: row.entity, ctype: row.ctype, attribute: "p", bus: row.bus, unit: "MW" }
        : null;
    columns.push({
      key: "dispatch",
      header: "Dispatch",
      description: "Power at its bus (its input for a line or link), from the run result",
      kind: "series",
      value: (row) => (dispatch(row) ? SERIES_VALUE : null),
      series: dispatch,
      render: (row) => {
        const series = dispatch(row);
        return series ? (
          <SeriesChip series={series} hours={ctx.hours} />
        ) : (
          <span className="text-surface-500">—</span>
        );
      },
    });
  }
  return columns;
}

// ------------------------------------------------------------ Component and carrier levels

export interface MemberEntry extends MemberRow {
  /** Stored values by attribute (several where it's per output bus). */
  values: Map<string, MemberValue[]>;
  /** MWh in the period (Inspect). */
  energy: number | null;
}

// Columns the table leads with, where a type stores them; the rest follow.
const PREFERRED = [
  "p_nom",
  "s_nom",
  "e_nom",
  "p_nom_extendable",
  "s_nom_extendable",
  "e_nom_extendable",
  "p_nom_min",
  "p_nom_max",
  "s_nom_max",
  "e_nom_max",
  "capital_cost",
  "marginal_cost",
  "efficiency",
  "lifetime",
  "build_year",
];
// Series (profiles) come after the constants.
const rank = (attribute: string, hasSeries: boolean) =>
  PREFERRED.includes(attribute)
    ? PREFERRED.indexOf(attribute)
    : PREFERRED.length + (hasSeries ? 1 : 0);

/** The member's own value: the one without a bus, else the one at its bus, else the first. */
function ownValue(entry: MemberEntry, attribute: string): MemberValue | undefined {
  const values = entry.values.get(attribute);
  if (!values?.length) return undefined;
  return (
    values.find((value) => value.bus === null) ??
    values.find((value) => value.bus === entry.bus) ??
    values[0]
  );
}

const isNumeric = (text: string | null) =>
  text === null || text === "" || text === "inf" || Number.isFinite(Number(text));

export function memberColumns(
  ctx: ColumnContext,
  entries: readonly MemberEntry[],
  ctype: string,
): TableColumn<MemberEntry>[] {
  const columns = entityColumns(ctx, entries, { component: false });
  const { manifest } = ctx;
  // Attributes some member stores, inputs first; results come after.
  const stored = new Map<string, { count: number; series: boolean; numeric: boolean }>();
  for (const entry of entries) {
    for (const [attribute, values] of entry.values) {
      const seen = stored.get(attribute) ?? { count: 0, series: false, numeric: true };
      seen.count += 1;
      seen.series ||= values.some((value) => value.series_rows > 0);
      seen.numeric &&= values.every((value) => isNumeric(value.constant));
      stored.set(attribute, seen);
    }
  }
  const capacity = componentKind(ctype).capacity;
  if (capacity && manifest.attributes[capacity] && !stored.has(capacity))
    stored.set(capacity, { count: 0, series: false, numeric: true });
  const inputs = [...stored.keys()]
    .filter((attribute) => manifest.attributes[attribute] && !ctx.results.has(attribute))
    .sort(
      (a, b) =>
        rank(a, stored.get(a)!.series) - rank(b, stored.get(b)!.series) ||
        stored.get(b)!.count - stored.get(a)!.count ||
        a.localeCompare(b),
    );

  for (const attribute of inputs) {
    const spec = manifest.attributes[attribute];
    const info = stored.get(attribute)!;
    const numeric =
      info.numeric && (spec.dtype === undefined || spec.dtype === "float" || spec.dtype === "int");
    const fallback = (entry: MemberEntry) => {
      const value = defaultFor(spec, entry.ctype);
      return value === null || value === undefined ? null : String(value);
    };
    const series = (entry: MemberEntry): PickedSeries | null => {
      const value = ownValue(entry, attribute);
      return value && value.series_rows > 0
        ? { entity: entry.entity, ctype: entry.ctype, attribute, bus: value.bus, unit: spec.unit }
        : null;
    };
    const text = (entry: MemberEntry) => {
      const value = ownValue(entry, attribute);
      return value ? value.constant : fallback(entry);
    };
    const change = (entry: MemberEntry) => {
      if (!ctx.changes) return undefined;
      const value = ownValue(entry, attribute);
      return ctx.changes.get(changeKey(attribute, "entity", entry.entity, value?.bus ?? null));
    };
    columns.push({
      key: `attr:${attribute}`,
      header: withUnit(attribute, spec.unit),
      description: spec.description,
      kind: info.series ? "series" : numeric ? "number" : "text",
      series: info.series ? series : undefined,
      value: (entry) => {
        if (series(entry)) return SERIES_VALUE;
        const value = text(entry);
        if (value === null || value === "") return null;
        if (!info.series && numeric) return value === "inf" ? Infinity : Number(value);
        return value;
      },
      render: (entry) => {
        const picked = series(entry);
        if (picked) return <SeriesChip series={picked} hours={ctx.hours} />;
        return formatValue(text(entry), { dtype: spec.dtype, unit: null });
      },
      cellClass: (entry) =>
        change(entry)
          ? CHANGED
          : ownValue(entry, attribute)
            ? "text-surface-300"
            : "text-surface-500 italic",
      cellTitle: (entry) =>
        changedTitle(ctx, change(entry), attribute) ??
        (ownValue(entry, attribute) ? undefined : "Default: not set for this entity"),
    });
  }

  if (ctx.inspect) {
    const kind = componentKind(ctype);
    if (kind.optimised) {
      const unit = unitOf(manifest, kind.capacity);
      columns.push({
        key: "optimised",
        header: withUnit(kind.optimised, unit),
        description: "From the run result",
        kind: "number",
        value: (entry) => entry.capacity_opt,
        render: (entry) => formatCell(entry.capacity_opt),
      });
    }
    if (kind.output && kind.outputRole)
      columns.push({
        key: "energy",
        header: `${kind.output} ${ctx.period} [TWh]`,
        description: `Energy in ${ctx.period}, weighted by snapshot_weighting_generators, from the run result`,
        kind: "number",
        value: (entry) => (entry.energy === null ? null : entry.energy / 1e6),
        render: (entry) => formatCell(entry.energy === null ? null : entry.energy / 1e6, 3),
      });
    const resultSeries = [...stored.entries()]
      .filter(([attribute, info]) => ctx.results.has(attribute) && info.series)
      .map(([attribute]) => attribute)
      .sort();
    for (const attribute of resultSeries) {
      const unit = unitOf(manifest, attribute) ?? (attribute === "p" ? "MW" : null);
      const series = (entry: MemberEntry): PickedSeries | null => {
        const values = entry.values.get(attribute)?.filter((value) => value.series_rows > 0) ?? [];
        const value = values.find((item) => item.bus === entry.bus) ?? values[0];
        return value
          ? { entity: entry.entity, ctype: entry.ctype, attribute, bus: value.bus, unit }
          : null;
      };
      columns.push({
        key: `result:${attribute}`,
        header: withUnit(attribute, unit),
        description: manifest.attributes[attribute]?.description ?? "From the run result",
        kind: "series",
        series,
        value: (entry) => (series(entry) ? SERIES_VALUE : null),
        render: (entry) => {
          const picked = series(entry);
          return picked ? (
            <SeriesChip series={picked} hours={ctx.hours} />
          ) : (
            <span className="text-surface-500">—</span>
          );
        },
      });
    }
  }
  return columns;
}

// ------------------------------------------------------------ All locations

export function locationColumns(ctx: ColumnContext): TableColumn<LocationRow>[] {
  const columns: TableColumn<LocationRow>[] = [
    {
      key: "location",
      header: "Location",
      kind: "text",
      maxChars: 40,
      value: (row) => row.location,
      render: (row) => (
        <span className="text-surface-100 flex min-w-0 items-center gap-1 font-mono text-[11.5px]">
          <LinkButton
            onClick={() => ctx.openLevel({ kind: "location", location: row.location })}
            title={row.location}
          >
            {row.location}
          </LinkButton>
          <CopyId text={row.location} />
        </span>
      ),
    },
    {
      key: "region",
      header: "Region",
      kind: "text",
      value: (row) => ctx.regionOf(row.location),
      render: (row) => ctx.regionOf(row.location) ?? <span className="text-surface-500">—</span>,
    },
    {
      key: "buses",
      header: "Buses",
      description: "One dot per bus, in its carrier’s colour",
      kind: "number",
      value: (row) => row.buses?.length ?? 0,
      render: (row) => (
        <span className="flex items-center gap-1">
          {(row.buses ?? []).map((item) => (
            <button
              key={item.bus}
              type="button"
              title={`${item.bus} (${ctx.carrier(item.carrier).name})`}
              aria-label={`Open bus ${item.bus}`}
              onClick={(event) => {
                event.stopPropagation();
                ctx.openLevel({ kind: "bus", bus: item.bus, location: row.location });
              }}
              className="hover:ring-accent-400 focus-visible:ring-accent-500 flex rounded-full outline-none hover:ring-1 focus-visible:ring-1"
            >
              <Dot color={ctx.carrier(item.carrier).color} />
            </button>
          ))}
        </span>
      ),
    },
    {
      key: "entities",
      header: "Entities",
      kind: "number",
      value: (row) => row.entities,
      render: (row) => formatCell(row.entities),
    },
    {
      key: "located",
      header: "Located",
      description: "Entities with a site of their own",
      kind: "number",
      value: (row) => row.located,
      render: (row) => formatCell(row.located),
    },
    {
      key: "gen_capacity",
      header: "Gen. capacity [MW]",
      kind: "number",
      value: (row) => row.gen_capacity,
      render: (row) => formatCell(row.gen_capacity),
    },
    {
      key: "peak_demand",
      header: "Peak demand [MW]",
      description: "Sum of the loads’ peak p_set in the time window",
      kind: "number",
      value: (row) => row.peak_demand,
      render: (row) => formatCell(row.peak_demand),
    },
    {
      key: "lines",
      header: "Lines",
      kind: "number",
      value: (row) => row.lines,
      render: (row) => formatCell(row.lines),
    },
  ];
  const demand = (row: LocationRow): PickedSeries | null =>
    row.demand_load
      ? { entity: row.demand_load, ctype: "Load", attribute: "p_set", bus: null, unit: "MW" }
      : null;
  columns.push({
    key: "demand",
    header: "Demand p_set",
    kind: "series",
    series: demand,
    value: (row) => (demand(row) ? SERIES_VALUE : null),
    render: (row) => {
      const series = demand(row);
      return series ? (
        <SeriesChip series={series} hours={ctx.hours} />
      ) : (
        <span className="text-surface-500">—</span>
      );
    },
  });
  if (ctx.inspect) {
    columns.push({
      key: "gen_capacity_opt",
      header: "Opt. gen. capacity [MW]",
      kind: "number",
      value: (row) => row.gen_capacity_opt,
      render: (row) => formatCell(row.gen_capacity_opt),
    });
    const price = (row: LocationRow): PickedSeries | null =>
      row.price_bus
        ? {
            entity: row.price_bus,
            ctype: "Bus",
            attribute: "marginal_price",
            bus: row.price_bus,
            unit: "€/MWh",
          }
        : null;
    columns.push({
      key: "marginal_price",
      header: "marginal_price [€/MWh]",
      description: "The price at the location’s own bus, from the run result",
      kind: "series",
      series: price,
      value: (row) => (price(row) ? SERIES_VALUE : null),
      render: (row) => {
        const series = price(row);
        return series ? (
          <SeriesChip series={series} hours={ctx.hours} />
        ) : (
          <span className="text-surface-500">—</span>
        );
      },
    });
  }
  return columns;
}
