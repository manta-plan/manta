import { useMemo } from "react";
import { useShownData } from "../../project/lib/record-data";
import {
  recordCatalog,
  serverName,
  serverQuery,
  sqlString,
} from "../../project/lib/record-server/client";
import { parseWktLineString, parseWktPolygonal, type WktPolygonal } from "../../project/lib/wkt";
import { ALL_ENTITIES, levelPageId, type Level } from "../level";
import { levelCtes, scopeKey, type LevelQueryScope } from "../level-sql";

// What the map and the graph read: the record's places (buses, regions,
// branches between locations, active in the period), what the level
// highlights, and the entities that have a location of their own.

export interface BusRow {
  bus: string;
  carrier: string | null;
  location: string;
  x: number;
  y: number;
}

export interface RegionRow {
  entity: string;
  /** 'onshore' or 'offshore' (or another the record names); null when untagged. */
  component: string | null;
  location: string | null;
  geometry: WktPolygonal;
}

/** A line, link or transformer between two locations, active in the period. */
export interface BranchRow {
  entity: string;
  ctype: string;
  carrier: string | null;
  bus0: string;
  bus1: string;
  location0: string;
  location1: string;
  capacity: number | null;
  capacity_opt: number | null;
}

/** The scope with the level's own filters off: what the whole map reads. */
export function baseScope(scope: LevelQueryScope): LevelQueryScope {
  return { level: ALL_ENTITIES, period: scope.period, timeWindow: scope.timeWindow, locations: [] };
}

/** The level without the map's location selection: what the map highlights. */
export function levelOnlyScope(scope: LevelQueryScope): LevelQueryScope {
  return { ...scope, locations: [] };
}

const num = (value: unknown) => (value === null || value === undefined ? null : Number(value));

function loadBuses(): Promise<BusRow[]> {
  return serverQuery<BusRow>(`
    SELECT bus, carrier, location, x, y FROM ${serverName("manta.bus_location")}
    WHERE NOT virtual ORDER BY location, bus`).then((rows) =>
    rows.map((row) => ({ ...row, x: Number(row.x), y: Number(row.y) })),
  );
}

/** Every real bus (virtual ones, such as EU, aren't places). */
export function useBuses() {
  return useShownData("side-buses", [], loadBuses);
}

async function loadRegions(): Promise<RegionRow[]> {
  const rows = await serverQuery<{
    entity: string;
    component: string | null;
    location: string | null;
    bus: string | null;
    wkt: string;
  }>(`SELECT entity, component, location, bus, wkt FROM ${serverName("manta.regions")}`);
  return rows.flatMap((row) => {
    const geometry = row.wkt ? parseWktPolygonal(row.wkt) : null;
    return geometry
      ? [
          {
            entity: row.entity,
            component: row.component,
            location: row.location ?? row.bus,
            geometry,
          },
        ]
      : [];
  });
}

/** Region shapes, tagged onshore or offshore. */
export function useRegions() {
  return useShownData("side-regions", [], loadRegions);
}

function loadBranches(scope: LevelQueryScope): Promise<BranchRow[]> {
  return serverQuery<BranchRow>(`
    WITH ${levelCtes(scope)}
    SELECT b.entity, b.ctype, b.carrier, b.bus0, b.bus1, b.location0, b.location1, e.capacity, e.capacity_opt
    FROM ${serverName("manta.branches")} b
    JOIN entities e ON e.entity = b.entity AND e.in_period
    WHERE b.scope = 'between'
    ORDER BY b.entity`).then((rows) =>
    rows.map((row) => ({
      ...row,
      capacity: num(row.capacity),
      capacity_opt: num(row.capacity_opt),
    })),
  );
}

/** Branches between locations, active in the period. */
export function useBranches(scope: LevelQueryScope | null) {
  const base = scope && baseScope(scope);
  return useShownData("side-branches", base ? [base.period] : null, () => loadBranches(base!));
}

// ------------------------------------------------------------ Highlight

export interface Highlight {
  /** Everything is highlighted (All entities, All locations). */
  all: boolean;
  /** Highlighted locations (the members' own, or the level's). */
  locations: Set<string>;
  /** Highlighted real buses. */
  buses: Set<string>;
  /** Lines that are members. */
  lines: Set<string>;
  /** Members at the level. */
  members: number;
}

interface HighlightRow {
  locations: string[] | null;
  buses: string[] | null;
  lines: string[] | null;
  members: number;
}

function loadHighlight(scope: LevelQueryScope): Promise<HighlightRow> {
  return serverQuery<HighlightRow>(`
    WITH ${levelCtes(scope)},
    nonline AS (SELECT * FROM members WHERE ctype <> 'Line')
    SELECT
      (SELECT list(DISTINCT location) FROM nonline WHERE location IS NOT NULL) AS locations,
      (SELECT list(DISTINCT u.bus) FROM (SELECT unnest(buses) AS bus FROM nonline) u
         JOIN ${serverName("manta.bus_location")} b ON b.bus = u.bus WHERE NOT b.virtual) AS buses,
      (SELECT list(entity) FROM members WHERE ctype = 'Line') AS lines,
      (SELECT count(*) FROM members)::INTEGER AS members`).then(
    (rows) => rows[0] ?? { locations: [], buses: [], lines: [], members: 0 },
  );
}

/** What the level highlights on the map: its members' buses and lines (the level's own location or bus in location mode). */
export function useHighlight(
  level: Level,
  scope: LevelQueryScope | null,
  buses: BusRow[] | null,
  branches: BranchRow[] | null,
): Highlight | null {
  const own = scope && levelOnlyScope(scope);
  const data = useShownData("side-highlight", own ? [scopeKey(own)] : null, () =>
    loadHighlight(own!),
  );
  const row = data.status === "ready" ? data.data : null;
  const key = levelPageId(level);
  // One object while nothing changed: the map rebuilds its features from it.
  return useMemo(
    // eslint-disable-next-line react-hooks/exhaustive-deps
    () => (row && buses ? highlightOf(level, row, buses, branches) : null),
    // level is new each render; its page id says when it changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, row, buses, branches],
  );
}

export function highlightOf(
  level: Level,
  row: HighlightRow,
  buses: BusRow[],
  branches: BranchRow[] | null,
): Highlight {
  const all = level.kind === "all-entities" || level.kind === "all-locations";
  if (all)
    return {
      all,
      locations: new Set(buses.map((bus) => bus.location)),
      buses: new Set(buses.map((bus) => bus.bus)),
      lines: new Set(branches?.filter((b) => b.ctype === "Line").map((b) => b.entity)),
      members: row.members,
    };
  const real = new Set(buses.map((bus) => bus.location));
  let locations = new Set((row.locations ?? []).filter((location) => real.has(location)));
  let busSet = new Set(row.buses ?? []);
  if (level.kind === "location") {
    locations = new Set([level.location]);
    busSet = new Set(buses.filter((bus) => bus.location === level.location).map((bus) => bus.bus));
  } else if (level.kind === "bus") {
    const location = level.location ?? buses.find((bus) => bus.bus === level.bus)?.location;
    locations = new Set(location ? [location] : []);
    busSet = new Set([level.bus]);
  } else if (level.kind === "entity") {
    // A Line (not counted above): both its ends.
    const line = branches?.find(
      (branch) => branch.entity === level.entity && branch.ctype === "Line",
    );
    if (line) {
      locations.add(line.location0);
      locations.add(line.location1);
      busSet.add(line.bus0);
      busSet.add(line.bus1);
    }
  }
  return { all, locations, buses: busSet, lines: new Set(row.lines ?? []), members: row.members };
}

// ------------------------------------------------------------ Entity geometry

// manta.entity_geometry (entity, ctype, carrier, kind 'point' | 'route' |
// 'area', wkt, lon, lat) is new on the server: a catalog without it has no
// siting, and says so once.
const missingGeometry = new Set<string>();

/** Whether a query failed because the relation isn't there (an older server), not because of a timeout or the like. */
export function isMissingRelation(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /does not exist|not found/i.test(message) && /entity_geometry/i.test(message);
}

async function readGeometry<T>(sql: string): Promise<T[] | null> {
  const catalog = recordCatalog() ?? "";
  if (missingGeometry.has(catalog)) return null;
  try {
    return await serverQuery<T>(sql);
  } catch (error) {
    // Anything but a missing relation (a timeout...) is thrown, so a later fetch retries.
    if (!isMissingRelation(error)) throw error;
    missingGeometry.add(catalog);
    console.warn(
      "No manta.entity_geometry on the record server: the map shows no entity siting.",
      error,
    );
    return null;
  }
}

export interface SiteRow {
  entity: string;
  ctype: string;
  carrier: string | null;
  /** The entity's bus's location: where its dashed line goes. */
  location: string | null;
  lon: number;
  lat: number;
}

function loadSites(scope: LevelQueryScope): Promise<SiteRow[] | null> {
  return readGeometry<SiteRow>(`
    WITH ${levelCtes(scope)}
    SELECT g.entity, m.ctype, m.carrier, m.location, g.lon, g.lat
    FROM ${serverName("manta.entity_geometry")} g
    JOIN members m USING (entity)
    WHERE g.kind = 'point' AND g.lon IS NOT NULL AND g.lat IS NOT NULL
    ORDER BY g.entity`).then(
    (rows) => rows && rows.map((row) => ({ ...row, lon: Number(row.lon), lat: Number(row.lat) })),
  );
}

/** The level's entities with a location of their own; null when the record has none to give. */
export function useSites(scope: LevelQueryScope | null) {
  const own = scope && levelOnlyScope(scope);
  return useShownData("side-sites", own ? [scopeKey(own)] : null, () => loadSites(own!));
}

/** A LINESTRING's or MULTILINESTRING's points, parts joined end to end: enough to draw a route. */
export function routePoints(wkt: string): [number, number][] {
  if (!/LINESTRING/i.test(wkt)) return [];
  const parts = wkt.match(/\(([^()]+)\)/g) ?? [];
  return parts.flatMap((part) => parseWktLineString(`LINESTRING${part}`));
}

async function loadRoutes(): Promise<Map<string, [number, number][]>> {
  const rows = await readGeometry<{ entity: string; wkt: string }>(
    `SELECT entity, wkt FROM ${serverName("manta.entity_geometry")} WHERE kind = 'route' AND wkt IS NOT NULL`,
  );
  const routes = new Map<string, [number, number][]>();
  for (const row of rows ?? []) {
    const points = routePoints(row.wkt);
    if (points.length >= 2) routes.set(row.entity, points);
  }
  return routes;
}

/** Each branch's own route, where the record has one. */
export function useRoutes() {
  return useShownData("side-routes", [], loadRoutes);
}

// ------------------------------------------------------------ Focus

export interface FocusTarget {
  entity: string;
  ctype: string;
  carrier: string | null;
  location: string | null;
  location1: string | null;
  site: [number, number] | null;
}

async function loadFocus(scope: LevelQueryScope, entity: string): Promise<FocusTarget | null> {
  const [rows, sites] = await Promise.all([
    serverQuery<Omit<FocusTarget, "site">>(`
      WITH ${levelCtes(scope)}
      SELECT entity, ctype, carrier, location, location1 FROM entities WHERE entity = ${sqlString(entity)}`),
    readGeometry<{ lon: number; lat: number }>(`
      SELECT lon, lat FROM ${serverName("manta.entity_geometry")}
      WHERE entity = ${sqlString(entity)} AND kind = 'point' AND lon IS NOT NULL AND lat IS NOT NULL LIMIT 1`),
  ]);
  const row = rows[0];
  if (!row) return null;
  const site = sites?.[0];
  return { ...row, site: site ? [Number(site.lon), Number(site.lat)] : null };
}

/** Where the entity the table asked about is: its site, its bus's location, a branch's ends. */
export function useFocusTarget(scope: LevelQueryScope | null, entity: string | null) {
  const base = scope && baseScope(scope);
  return useShownData("side-focus", base && entity ? [base.period, entity] : null, () =>
    loadFocus(base!, entity!),
  );
}

// ------------------------------------------------------------ Area name

async function loadAreaName(): Promise<string | null> {
  const rows = await serverQuery<{ country: string }>(
    `SELECT DISTINCT country FROM ${serverName("properties.bus")} WHERE country IS NOT NULL AND country <> ''`,
  ).catch(() => []);
  if (rows.length !== 1) return null;
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(rows[0].country) ?? rows[0].country;
  } catch {
    return rows[0].country;
  }
}

/** The record's country, when all its buses are in one ("Belgium"); null otherwise. */
export function useAreaName(): string | null {
  const data = useShownData("side-area", [], loadAreaName);
  return data.status === "ready" ? data.data : null;
}
