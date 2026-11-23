import { useMemo } from "react";
import { useShownData } from "../../project/lib/record-data";
import type { LoadedRecord } from "../../project/store/types";
import { useProjectStore } from "../../project/store/project-store";
import type { Level } from "../level";
import { useLevelPage } from "../level-page-context";
import { scopeKey, type LevelQueryScope } from "../level-sql";
import { AttributesTable } from "./attributes-table";
import { useCarrierInfo } from "./format";
import type { TableColumn } from "./columns";
import { DataTable } from "./data-table";
import {
  locationColumns,
  memberColumns,
  mixedColumns,
  type ColumnContext,
  type MemberEntry,
} from "./level-columns";
import {
  loadLocationRows,
  loadMemberEnergy,
  loadMemberRows,
  loadMemberValues,
  loadMixedRows,
  loadSpanHours,
  type HasView,
  type LocationRow,
  type MemberValue,
  type MixedRow,
} from "./table-queries";

// The level's table, filling the split's left: its members (entities active
// in the period, at the level, at the locations picked on the map), all
// locations, or one entity's attributes.

// Result attributes where the revision doesn't list them.
const RESULT_ATTRIBUTES = [
  "p",
  "p0",
  "p1",
  "q",
  "e",
  "p_nom_opt",
  "s_nom_opt",
  "e_nom_opt",
  "marginal_price",
  "mu",
  "state_of_charge",
  "p_dispatch",
  "p_store",
  "spill",
];

/** The region level the Region column reads: the one with the fewest distinct zones above one. */
function useRegionOf(record: LoadedRecord | null) {
  const zones = record?.zones;
  return useMemo(() => {
    const byLevel = new Map<string, Map<string, string>>();
    for (const zone of zones ?? []) {
      const level = byLevel.get(zone.level) ?? new Map<string, string>();
      level.set(zone.location, zone.zone);
      byLevel.set(zone.level, level);
    }
    let best: Map<string, string> | null = null;
    let bestCount = Infinity;
    for (const level of byLevel.values()) {
      const count = new Set(level.values()).size;
      if (count > 1 && count < bestCount) {
        best = level;
        bestCount = count;
      }
    }
    return (location: string) => best?.get(location) ?? null;
  }, [zones]);
}

export function LevelTable() {
  const { level, stage, result, scope, openLevel } = useLevelPage();
  const record = useProjectStore((s) => s.record);
  const carrierInfo = useCarrierInfo();
  const regionOf = useRegionOf(record);
  const inspect = stage === "inspect" && result !== null;

  const results = useMemo(() => {
    if (!inspect || !record) return new Set<string>();
    const revision = record.info.revisions.find(
      (item) => item.name === result.id || item.id === result.id,
    );
    return new Set(revision?.results.length ? revision.results : RESULT_ATTRIBUTES);
  }, [inspect, record, result]);
  const hasView = useMemo<HasView>(() => {
    const views = new Set([...(record?.info.views.attributes ?? []), ...results]);
    return (attribute) => views.has(attribute);
  }, [record, results]);

  const hoursData = useShownData(
    "level-table-hours",
    scope ? [scope.period, scope.timeWindow?.start ?? null, scope.timeWindow?.end ?? null] : null,
    () => loadSpanHours(scope!, hasView),
  );
  const hours = hoursData.status === "ready" ? hoursData.data : 0;

  const period = scope?.period ?? null;
  const ctx = useMemo<ColumnContext | null>(() => {
    if (!record || period === null) return null;
    const shown = record.info.revisions.find((revision) => revision.name === record.scenario);
    const parent = record.info.revisions.find((revision) => revision.name === shown?.parent);
    return {
      level,
      inspect,
      hours,
      period,
      carrier: carrierInfo,
      openLevel,
      manifest: record.info.manifest,
      // Markers are for a scenario's own edits: Build only.
      changes: stage === "build" && record.changes.size > 0 ? record.changes : null,
      parentLabel: parent?.label ?? "its parent",
      results,
      regionOf,
    };
  }, [record, period, level, inspect, hours, carrierInfo, openLevel, stage, results, regionOf]);

  if (level.kind === "entity")
    return (
      <AttributesTable
        entity={level.entity}
        inspect={inspect}
        results={results}
        hours={hours}
        changes={ctx?.changes ?? null}
        parentLabel={ctx?.parentLabel ?? ""}
      />
    );
  const title = level.kind === "all-locations" ? "Locations" : "Entities";
  if (!ctx || !scope)
    return (
      <DataTable
        title={title}
        noun={title.toLowerCase()}
        columns={[]}
        rows={[]}
        rowKey={() => ""}
        status="Loading…"
      />
    );
  if (level.kind === "all-locations")
    return <LocationsTable scope={scope} ctx={ctx} hasView={hasView} />;
  if (level.kind === "component" || level.kind === "carrier")
    return <MembersTable scope={scope} ctx={ctx} ctype={level.ctype} />;
  return <MixedTable scope={scope} ctx={ctx} hasView={hasView} />;
}

type DataState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; refreshing: boolean };

function statusOf(data: DataState, what: string) {
  if (data.status === "loading") return `Loading ${what}…`;
  if (data.status === "error") return `Couldn't load the ${what}: ${data.error}`;
  return undefined;
}

const EMPTY_MIXED: MixedRow[] = [];
const EMPTY_LOCATIONS: LocationRow[] = [];

function MixedTable({
  scope,
  ctx,
  hasView,
}: {
  scope: LevelQueryScope;
  ctx: ColumnContext;
  hasView: HasView;
}) {
  const data = useShownData("level-table-mixed", [scopeKey(scope)], () =>
    loadMixedRows(scope, hasView),
  );
  const rows = data.status === "ready" ? data.data : EMPTY_MIXED;
  const columns = useMemo(() => mixedColumns(ctx, rows), [ctx, rows]);
  return <EntityTable data={data} rows={rows} columns={columns} openLevel={ctx.openLevel} />;
}

function MembersTable({
  scope,
  ctx,
  ctype,
}: {
  scope: LevelQueryScope;
  ctx: ColumnContext;
  ctype: string;
}) {
  const key = scopeKey(scope);
  const members = useShownData("level-table-members", [key], () => loadMemberRows(scope));
  const values = useShownData("level-table-values", [key], () => loadMemberValues(scope));
  const energy = useShownData("level-table-energy", ctx.inspect ? [key, ctype] : null, () =>
    loadMemberEnergy(scope, ctype),
  );
  const energyMap = energy.status === "ready" ? energy.data : null;
  const memberRows = members.status === "ready" ? members.data : null;
  const valueRows = values.status === "ready" ? values.data : null;
  const entries = useMemo<MemberEntry[]>(() => {
    if (!memberRows || !valueRows) return [];
    const byEntity = new Map<string, Map<string, MemberValue[]>>();
    for (const value of valueRows) {
      const attributes = byEntity.get(value.entity) ?? new Map<string, MemberValue[]>();
      const list = attributes.get(value.attribute) ?? [];
      list.push(value);
      attributes.set(value.attribute, list);
      byEntity.set(value.entity, attributes);
    }
    return memberRows.map((row) => ({
      ...row,
      values: byEntity.get(row.entity) ?? new Map<string, MemberValue[]>(),
      energy: energyMap?.get(row.entity) ?? null,
    }));
  }, [memberRows, valueRows, energyMap]);
  const columns = useMemo(() => memberColumns(ctx, entries, ctype), [ctx, entries, ctype]);
  const state: DataState =
    members.status !== "ready"
      ? members
      : values.status !== "ready"
        ? values
        : { status: "ready", refreshing: members.refreshing || values.refreshing };
  return <EntityTable data={state} rows={entries} columns={columns} openLevel={ctx.openLevel} />;
}

function EntityTable<R extends { entity: string }>({
  data,
  rows,
  columns,
  openLevel,
}: {
  data: DataState;
  rows: readonly R[];
  columns: TableColumn<R>[];
  openLevel: (level: Level) => void;
}) {
  return (
    <DataTable
      title="Entities"
      noun="entities"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.entity}
      onOpenRow={(row) => openLevel({ kind: "entity", entity: row.entity })}
      openLabel={(row) => `Open ${row.entity}`}
      isRefreshing={data.status === "ready" && data.refreshing}
      status={statusOf(data, "entities")}
    />
  );
}

function LocationsTable({
  scope,
  ctx,
  hasView,
}: {
  scope: LevelQueryScope;
  ctx: ColumnContext;
  hasView: HasView;
}) {
  const data = useShownData("level-table-locations", [scopeKey(scope)], () =>
    loadLocationRows(scope, hasView),
  );
  const rows = data.status === "ready" ? data.data : EMPTY_LOCATIONS;
  const columns = useMemo(() => locationColumns(ctx), [ctx]);
  return (
    <DataTable
      title="Locations"
      noun="locations"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.location}
      onOpenRow={(row) => ctx.openLevel({ kind: "location", location: row.location })}
      openLabel={(row) => `Open ${row.location}`}
      isRefreshing={data.status === "ready" && data.refreshing}
      status={statusOf(data, "locations")}
    />
  );
}
