// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { fetchApi, recordCatalog, serverName, serverQuery, sqlName, sqlString } from "./client";
import type {
  AttributeSpec,
  Carrier,
  EntityAttribute,
  EntityConnection,
  EntityCount,
  EntityDetail,
  EntityPlace,
  LabelDetail,
  Location,
  LocationZone,
  Manifest,
  RecordInfo,
  ScenarioChange,
  ScenarioChangeSummary,
  ScenarioChangeValue,
} from "./types";

// Typed reads of the record, in the active scenario's catalog (serverName).
// Every read runs on the server (serverQuery): records open on demand, and the
// browser's attached `r` only lists the catalogs that existed when it
// attached. It also means only the result travels.

// Opens the record if it isn't yet; with `revision`, that run result too.
export function openRecord(id: string, revision?: string): Promise<RecordInfo> {
  const query = revision ? `?revision=${encodeURIComponent(revision)}` : "";
  return fetchApi<RecordInfo>(`/api/records/${encodeURIComponent(id)}/open${query}`, "POST");
}

export function getCarriers(): Promise<Carrier[]> {
  return serverQuery<Carrier>(
    `SELECT carrier, color, nice_name AS "niceName" FROM ${serverName("properties.carrier")}`,
  );
}

export function getEntityCounts(): Promise<EntityCount[]> {
  return serverQuery<EntityCount>(
    `SELECT ctype, carrier, count(*) AS entities FROM ${serverName("properties.entity")} GROUP BY ALL ORDER BY ALL`,
  );
}

export function getLocations(): Promise<Location[]> {
  return serverQuery<Location>(`FROM ${serverName("manta.locations")} ORDER BY location`);
}

export function getLocationZones(): Promise<LocationZone[]> {
  return serverQuery<LocationZone>(`FROM ${serverName("manta.location_zones")}`);
}

// Entities with where each is: its bus's location, a branch's input location
// (and its outputs), or a Shape's.
export async function getEntityListItem(entity: string): Promise<EntityPlace | null> {
  const rows = await serverQuery<EntityPlace>(`
    SELECT e.entity, e.ctype, e.carrier,
           coalesce(a.location, b.location0, g.location) AS location,
           coalesce(b.outputs, []) AS outputs
    FROM ${serverName("properties.entity")} e
    LEFT JOIN ${serverName("manta.attached")} a USING (entity)
    LEFT JOIN (SELECT entity, any_value(location0) AS location0, list(DISTINCT location1 ORDER BY location1) AS outputs
               FROM ${serverName("manta.branches")} GROUP BY entity) b USING (entity)
    LEFT JOIN (SELECT entity, any_value(location) AS location FROM ${serverName("manta.regions")} GROUP BY entity) g USING (entity)
    WHERE e.entity = ${sqlString(entity)}`);
  return rows[0] ?? null;
}

// The manifest default for one entity: a `default_by` rule on its ctype wins.
export function defaultFor(spec: AttributeSpec, ctype: string): unknown {
  const byCtype = spec.default_by["entity.ctype"];
  return byCtype && ctype in byCtype ? byCtype[ctype] : spec.default;
}

const usedByCtype = new Map<string, Promise<Set<string>>>();

// Attributes this ctype has values for somewhere in the record: where an
// entity without a value reads the default, rather than the attribute not
// applying to it at all (the manifest doesn't say which ctype uses what).
// Per scenario: a scenario may store values the base case leaves default.
function attributesUsedBy(ctype: string): Promise<Set<string>> {
  const key = `${recordCatalog() ?? ""}\n${ctype}`;
  let used = usedByCtype.get(key);
  if (!used) {
    used = serverQuery<{ attribute: string }>(
      `SELECT attribute FROM ${serverName("manta.ctype_attributes")} WHERE ctype = ${sqlString(ctype)}`,
    ).then((rows) => new Set(rows.map((row) => row.attribute)));
    usedByCtype.set(key, used);
  }
  return used;
}

export async function getEntity(entity: string, manifest: Manifest): Promise<EntityDetail | null> {
  const id = sqlString(entity);
  const [[properties], connections, values] = await Promise.all([
    serverQuery<Record<string, unknown>>(
      `FROM ${serverName("properties.entity")} WHERE entity = ${id}`,
    ),
    serverQuery<EntityConnection>(`
      SELECT c.connection.bus AS bus, c.role, b.location, b.carrier AS "busCarrier"
      FROM ${serverName("properties.connection")} c JOIN ${serverName("manta.bus_location")} b ON b.bus = c.connection.bus
      WHERE c.connection.entity = ${id}
      ORDER BY c.role, c.connection.bus`),
    serverQuery<{
      attribute: string;
      bus: string | null;
      constant: string | null;
      seriesRows: number;
    }>(`
      SELECT attribute, bus, constant, series_rows AS "seriesRows"
      FROM ${serverName("manta.attribute_summary")} WHERE dim = 'entity' AND label = ${id}`),
  ]);
  if (!properties) return null;

  const ctype = String(properties.ctype);
  const used = await attributesUsedBy(ctype);
  const stored = new Set(values.map((row) => row.attribute));
  const attributes: EntityAttribute[] = values
    .filter((row) => manifest.attributes[row.attribute])
    .map((row) => ({
      name: row.attribute,
      spec: manifest.attributes[row.attribute],
      bus: row.bus,
      value: row.constant,
      isDefault: false,
      seriesRows: row.seriesRows,
    }));
  for (const name of used) {
    const spec = manifest.attributes[name];
    if (stored.has(name) || !spec) continue;
    const fallback = defaultFor(spec, ctype);
    attributes.push({
      name,
      spec,
      bus: null,
      value: fallback == null ? null : String(fallback),
      isDefault: true,
      seriesRows: 0,
    });
  }
  attributes.sort(
    (a, b) => a.name.localeCompare(b.name) || (a.bus ?? "").localeCompare(b.bus ?? ""),
  );
  return { entity, properties, connections, attributes };
}

function summaryAttributes(
  rows: { attribute: string; bus: string | null; constant: string | null; seriesRows: number }[],
  manifest: Manifest,
): EntityAttribute[] {
  return rows
    .filter((row) => manifest.attributes[row.attribute])
    .map((row) => ({
      name: row.attribute,
      spec: manifest.attributes[row.attribute],
      bus: row.bus,
      value: row.constant,
      isDefault: false,
      seriesRows: row.seriesRows,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// Per scenario, the attributes it changes: what the Scenarios panel lists.
export function getScenarioChanges(): Promise<ScenarioChangeSummary[]> {
  return serverQuery<ScenarioChangeSummary>(`
    SELECT scenario, attribute, dim, count(DISTINCT (label, bus)) AS subjects,
           sum(series_rows) AS "seriesRows", median(ratio) AS ratio
    FROM ${serverName("manta.scenario_changes")} GROUP BY ALL ORDER BY scenario, attribute`);
}

// One change in full: each entity or bus, with where it is. Every catalog of
// a record holds the changes of all its scenarios; the joins read the shown
// scenario's network.
export function getScenarioChange(scenario: string, attribute: string): Promise<ScenarioChange[]> {
  return serverQuery<ScenarioChange>(`
    SELECT c.dim, c.label, c.bus, c.before, c.after, c.series_rows AS "seriesRows", c.ratio,
           e.ctype, e.carrier, coalesce(a.location, br.location0, bl.location) AS location
    FROM ${serverName("manta.scenario_changes")} c
    LEFT JOIN ${serverName("properties.entity")} e ON c.dim = 'entity' AND e.entity = c.label
    LEFT JOIN ${serverName("manta.attached")} a ON c.dim = 'entity' AND a.entity = c.label
    LEFT JOIN (SELECT entity, any_value(location0) AS location0 FROM ${serverName("manta.branches")} GROUP BY entity) br
      ON c.dim = 'entity' AND br.entity = c.label
    LEFT JOIN ${serverName("manta.bus_location")} bl ON c.dim = 'bus' AND bl.bus = c.label
    WHERE c.scenario = ${sqlString(scenario)} AND c.attribute = ${sqlString(attribute)}
    ORDER BY c.label, c.bus`);
}

// Every value one scenario changes, keyed by changeKey: the markers in the
// drawers and the entity table.
export async function getScenarioChangeValues(
  scenario: string,
): Promise<Map<string, ScenarioChangeValue>> {
  const rows = await serverQuery<
    ScenarioChangeValue & { attribute: string; dim: string; label: string; bus: string | null }
  >(`
    SELECT attribute, dim, label, bus, before, after, series_rows AS "seriesRows", ratio
    FROM ${serverName("manta.scenario_changes")} WHERE scenario = ${sqlString(scenario)}`);
  return new Map(
    rows.map(({ attribute, dim, label, bus, ...value }) => [
      changeKey(attribute, dim, label, bus),
      value,
    ]),
  );
}

export function changeKey(
  attribute: string,
  dim: string,
  label: string,
  bus: string | null,
): string {
  return [attribute, dim, label, bus ?? ""].join("\n");
}

// A label of a dimension other than entity (a bus, a carrier, a snapshot, …):
// its properties and the attributes stored over it.
export async function getLabelDetail(
  dim: string,
  label: string,
  info: RecordInfo,
): Promise<LabelDetail> {
  const [labels, values] = await Promise.all([
    info.views.properties?.includes(dim)
      ? serverQuery<Record<string, unknown>>(
          `FROM ${serverName(`properties.${sqlName(dim)}`)} WHERE ${sqlName(dim)}::VARCHAR = ${sqlString(label)}`,
        )
      : Promise.resolve([]),
    serverQuery<{
      attribute: string;
      bus: string | null;
      constant: string | null;
      seriesRows: number;
    }>(`
      SELECT attribute, bus, constant, series_rows AS "seriesRows"
      FROM ${serverName("manta.attribute_summary")} WHERE dim = ${sqlString(dim)} AND label = ${sqlString(label)}`),
  ]);
  const { [dim]: value, ...properties } = labels[0] ?? {};
  // A connection's values are summarised per entity and bus, not per label.
  if (dim === "connection" && value && typeof value === "object") {
    const { entity, bus } = value as { entity: string; bus: string };
    const rows = await serverQuery<{
      attribute: string;
      bus: string | null;
      constant: string | null;
      seriesRows: number;
    }>(`
      SELECT attribute, bus, constant, series_rows AS "seriesRows"
      FROM ${serverName("manta.attribute_summary")} WHERE dim = 'entity' AND label = ${sqlString(entity)} AND bus = ${sqlString(bus)}`);
    return {
      dim,
      label,
      properties: { entity, bus, ...properties },
      attributes: summaryAttributes(rows, info.manifest),
    };
  }
  return { dim, label, properties, attributes: summaryAttributes(values, info.manifest) };
}
