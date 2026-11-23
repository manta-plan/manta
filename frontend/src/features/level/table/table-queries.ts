import { serverName, serverQuery, sqlString } from "../../project/lib/record-server/client";
import { levelCtes, spanCondition, type LevelQueryScope } from "../level-sql";

// The table's reads, one per kind of level (SQL tab, "Entity table" 4.2 to
// 4.4). Filtering, sorting and statistics run in the browser over the rows:
// a level has at most a few thousand.
//
// Geolocation comes from manta.entity_geometry ('point' a site of its own,
// 'route' a line's path). Servers without that view yet answer the same
// query without it: no Geolocated information rather than an error.

export type GeometryKind = "point" | "route" | null;

/** One member at a mixed level (All entities, a location, a bus). */
export interface MixedRow {
  entity: string;
  ctype: string;
  carrier: string | null;
  bus: string | null;
  bus1: string | null;
  location: string | null;
  location1: string | null;
  cap_attribute: string | null;
  capacity: number | null;
  capacity_opt: number | null;
  status: string | null;
  geometry: GeometryKind;
  /** p_max_pu (p_set for a load): which, its constant, and how many series rows it has. */
  profile: string | null;
  profile_constant: string | null;
  profile_rows: number;
  /** A load's peak p_set in the window (MW). */
  peak: number | null;
  /** Rows of the result's power at the entity's (input) bus; 0 on Build. */
  dispatch_rows: number;
}

/** One member at a component or carrier level; its attributes come apart (one row per attribute value). */
export interface MemberRow {
  entity: string;
  ctype: string;
  carrier: string | null;
  bus: string | null;
  bus1: string | null;
  location: string | null;
  location1: string | null;
  cap_attribute: string | null;
  capacity_opt: number | null;
  status: string | null;
  geometry: GeometryKind;
}

/** One stored attribute of one member. */
export interface MemberValue {
  entity: string;
  attribute: string;
  bus: string | null;
  constant: string | null;
  series_rows: number;
}

export interface LocationRow {
  location: string;
  buses: { bus: string; carrier: string | null }[] | null;
  entities: number;
  located: number;
  gen_capacity: number | null;
  gen_capacity_opt: number | null;
  peak_demand: number | null;
  lines: number;
  /** A load there with a p_set series: the Demand p_set chip picks it. */
  demand_load: string | null;
  /** The location's own bus where it has a marginal price series (Inspect). */
  price_bus: string | null;
}

/** Whether the shown catalog (or the result) has an attribute view. */
export type HasView = (attribute: string) => boolean;

const props = () => `props AS (
  SELECT p.entity, json_extract_string(to_json(p), '$.asset_status') AS status
  FROM ${serverName("properties.entity")} p)`;

export const geometryCte = (withGeometry: boolean) =>
  withGeometry
    ? `geo AS (SELECT entity, any_value(kind) AS kind FROM ${serverName("manta.entity_geometry")} WHERE kind IN ('point', 'route') GROUP BY entity)`
    : `geo AS (SELECT NULL::VARCHAR AS entity, NULL::VARCHAR AS kind WHERE false)`;

/** A load's peak p_set over the window; a constant p_set counts for every snapshot. */
export function peaksCte(scope: LevelQueryScope, from: "members" | "entities", hasView: HasView) {
  if (!hasView("p_set"))
    return `peaks AS (SELECT NULL::VARCHAR AS entity, NULL::DOUBLE AS peak WHERE false)`;
  return `peaks AS (
    SELECT a.entity, max(a.value) AS peak FROM ${serverName("attributes.p_set")} a JOIN ${from} m ON m.entity = a.entity
    WHERE m.ctype = 'Load'${from === "entities" ? " AND m.in_period" : ""} AND (a.snapshot IS NULL OR (${spanCondition("a.snapshot", scope.period, scope.timeWindow)}))
    GROUP BY 1)`;
}

/** Runs the query with entity_geometry, or without it where the server has none. */
let warnedNoGeometry = false;

/** The one console warning a missing manta.entity_geometry costs (the reads go on without it). */
function warnNoGeometry() {
  if (warnedNoGeometry) return;
  warnedNoGeometry = true;
  console.warn(
    "manta.entity_geometry is missing on this record server: the table has no Geolocated information.",
  );
}

export async function withGeometry<T>(build: (withGeometry: boolean) => string): Promise<T[]> {
  try {
    return await serverQuery<T>(build(true));
  } catch (error) {
    if (!/entity_geometry/i.test(String(error instanceof Error ? error.message : error)))
      throw error;
    warnNoGeometry();
    return serverQuery<T>(build(false));
  }
}

export function loadMixedRows(scope: LevelQueryScope, hasView: HasView): Promise<MixedRow[]> {
  const summary = serverName("manta.attribute_summary");
  return withGeometry<MixedRow>(
    (geometry) => `
    WITH ${levelCtes(scope)},
    ${props()},
    ${geometryCte(geometry)},
    summary AS (
      SELECT s.label AS entity, s.attribute, s.bus, s.constant, s.series_rows
      FROM ${summary} s JOIN members m ON m.entity = s.label
      WHERE s.dim = 'entity' AND s.attribute IN ('p_max_pu', 'p_set', 'p')),
    ${peaksCte(scope, "members", hasView)}
    SELECT m.entity, m.ctype, m.carrier, m.bus, m.bus1, m.location, m.location1, m.cap_attribute,
           m.capacity::DOUBLE AS capacity, m.capacity_opt::DOUBLE AS capacity_opt,
           g.status, geo.kind AS geometry,
           pr.attribute AS profile, pr.constant AS profile_constant, coalesce(pr.series_rows, 0)::INTEGER AS profile_rows,
           w.peak::DOUBLE AS peak,
           coalesce(d.series_rows, 0)::INTEGER AS dispatch_rows
    FROM members m
    LEFT JOIN props g USING (entity)
    LEFT JOIN geo ON geo.entity = m.entity
    LEFT JOIN summary pr ON pr.entity = m.entity AND pr.bus IS NULL AND pr.attribute = CASE WHEN m.ctype = 'Load' THEN 'p_set' ELSE 'p_max_pu' END
    LEFT JOIN summary d ON d.entity = m.entity AND d.attribute = 'p' AND d.bus = m.bus
    LEFT JOIN peaks w ON w.entity = m.entity
    ORDER BY m.ctype, m.entity`,
  );
}

export function loadMemberRows(scope: LevelQueryScope): Promise<MemberRow[]> {
  return withGeometry<MemberRow>(
    (geometry) => `
    WITH ${levelCtes(scope)},
    ${props()},
    ${geometryCte(geometry)}
    SELECT m.entity, m.ctype, m.carrier, m.bus, m.bus1, m.location, m.location1, m.cap_attribute,
           m.capacity_opt::DOUBLE AS capacity_opt, g.status, geo.kind AS geometry
    FROM members m
    LEFT JOIN props g USING (entity)
    LEFT JOIN geo ON geo.entity = m.entity
    ORDER BY m.entity`,
  );
}

export function loadMemberValues(scope: LevelQueryScope): Promise<MemberValue[]> {
  return serverQuery<MemberValue>(`
    WITH ${levelCtes(scope)}
    SELECT s.label AS entity, s.attribute, s.bus, s.constant, s.series_rows::INTEGER AS series_rows
    FROM ${serverName("manta.attribute_summary")} s JOIN members m ON m.entity = s.label
    WHERE s.dim = 'entity'`);
}

/** What counts as output, per type: its connection role and how power counts (as componentPage's kinds). */
const OUTPUT: Record<string, { role: string; value: string }> = {
  Generator: { role: "attached", value: "p.value" },
  StorageUnit: { role: "attached", value: "greatest(p.value, 0)" },
  Link: { role: "input", value: "p.value" },
  Line: { role: "input", value: "abs(p.value)" },
  Transformer: { role: "input", value: "abs(p.value)" },
  Load: { role: "attached", value: "p.value" },
};

/** Each member's output in the period (MWh), weighted by snapshot_weighting_generators. Inspect only. */
export async function loadMemberEnergy(
  scope: LevelQueryScope,
  ctype: string,
): Promise<Map<string, number>> {
  const output = OUTPUT[ctype];
  if (!output) return new Map();
  const rows = await serverQuery<{ entity: string; energy: number }>(`
    WITH ${levelCtes(scope)}
    SELECT p.connection.entity AS entity, sum(${output.value} * w.value)::DOUBLE AS energy
    FROM ${serverName("attributes.p")} p
    JOIN members m ON m.entity = p.connection.entity
    JOIN ${serverName("properties.connection")} c ON c.connection = p.connection
    JOIN ${serverName("attributes.snapshot_weighting_generators")} w ON w.snapshot = p.snapshot
    WHERE c.role = ${sqlString(output.role)} AND p.snapshot.period::VARCHAR = ${sqlString(scope.period)}
    GROUP BY 1`);
  return new Map(rows.map((row) => [row.entity, Number(row.energy)]));
}

export function loadLocationRows(scope: LevelQueryScope, hasView: HasView): Promise<LocationRow[]> {
  const summary = serverName("manta.attribute_summary");
  const selected = scope.locations?.length
    ? `WHERE l.location IN (${scope.locations.map(sqlString).join(", ")})`
    : "";
  return withGeometry<LocationRow>(
    (geometry) => `
    WITH ${levelCtes(scope)},
    ${geometryCte(geometry)},
    ${peaksCte(scope, "entities", hasView)},
    demand AS (SELECT label AS entity FROM ${summary} WHERE dim = 'entity' AND attribute = 'p_set' AND bus IS NULL AND series_rows > 0),
    at_location AS (
      SELECT location, list({'bus': bus, 'carrier': carrier} ORDER BY bus) AS buses
      FROM ${serverName("manta.bus_location")} WHERE NOT virtual GROUP BY 1),
    price AS (SELECT DISTINCT label AS bus FROM ${summary} WHERE dim = 'bus' AND attribute = 'marginal_price' AND series_rows > 0)
    SELECT l.location, b.buses,
           count(DISTINCT e.entity)::INTEGER AS entities,
           (count(DISTINCT e.entity) FILTER (WHERE geo.kind = 'point'))::INTEGER AS located,
           (sum(e.capacity) FILTER (WHERE e.ctype = 'Generator'))::DOUBLE AS gen_capacity,
           (sum(e.capacity_opt) FILTER (WHERE e.ctype = 'Generator'))::DOUBLE AS gen_capacity_opt,
           (sum(w.peak) FILTER (WHERE e.ctype = 'Load'))::DOUBLE AS peak_demand,
           (count(DISTINCT e.entity) FILTER (WHERE e.ctype = 'Line'))::INTEGER AS lines,
           min(e.entity) FILTER (WHERE e.ctype = 'Load' AND d.entity IS NOT NULL) AS demand_load,
           any_value(pb.bus) AS price_bus
    FROM ${serverName("manta.locations")} l
    LEFT JOIN at_location b USING (location)
    LEFT JOIN entities e ON e.in_period AND list_contains(e.locations, l.location)
    LEFT JOIN geo ON geo.entity = e.entity
    LEFT JOIN peaks w ON w.entity = e.entity
    LEFT JOIN demand d ON d.entity = e.entity
    LEFT JOIN price pb ON pb.bus = l.location
    ${selected}
    GROUP BY l.location, b.buses
    ORDER BY l.location`,
  );
}

/** Hours the window's snapshots stand for (snapshot_weighting_generators; else one per snapshot): the "· n h" on series chips. */
export async function loadSpanHours(scope: LevelQueryScope, hasView: HasView): Promise<number> {
  const weighted = hasView("snapshot_weighting_generators");
  const rows = await serverQuery<{ hours: number }>(`
    WITH ${levelCtes(scope)}
    SELECT ${weighted ? "coalesce(sum(w.value), count(*))" : "count(*)"}::DOUBLE AS hours
    FROM span s ${weighted ? `LEFT JOIN ${serverName("attributes.snapshot_weighting_generators")} w ON w.snapshot = s.snapshot` : ""}`);
  return Number(rows[0]?.hours ?? 0);
}

/** One entity's geometry as stored (WKT), its asset status and technology group, where the record has them. */
export async function loadEntityDims(entity: string): Promise<{
  status: string | null;
  technology_group: string | null;
  geometry: string | null;
} | null> {
  const rows = await serverQuery<{
    status: string | null;
    technology_group: string | null;
    geometry: string | null;
  }>(`
    SELECT json_extract_string(to_json(p), '$.asset_status') AS status,
           json_extract_string(to_json(p), '$.technology_group') AS technology_group,
           nullif(trim(json_extract_string(to_json(p), '$.geometry')), '') AS geometry
    FROM ${serverName("properties.entity")} p WHERE p.entity = ${sqlString(entity)}`);
  return rows[0] ?? null;
}
