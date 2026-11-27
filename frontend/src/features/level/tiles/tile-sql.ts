// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { serverName, sqlString } from "../../project/lib/record-server/client";
import { levelFilter, type Level } from "../level";
import { levelCtes, spanCondition, type LevelQueryScope } from "../level-sql";

// The tiles' SQL (the handover's 5.1–5.6): one query of the inputs and, on
// Inspect, one of the run result, each a single row whose nested parts are
// JSON text. Parts a level doesn't show are left out, so a type page doesn't
// pay for another type's figures.
//
// Hour-summed figures follow the time window and are scaled to a year: the
// window's weighted hours (snapshot_weighting_generators, 1 where missing)
// stand for the period's. A constant p_set or p_max_pu counts for every
// snapshot in the window.

/** Which parts of the inputs query a level needs. */
export interface InputParts {
  volumes: boolean;
  load: boolean;
  /** Build's estimate of the generators' capacity factor (5.5). */
  capacityFactor: boolean;
  /** The round trip of the links charging and discharging the level's stores. */
  storeEfficiency: boolean;
  /** The level's one entity, with its own attributes. */
  entity: boolean;
  /** Locations, buses and regions (All locations). */
  locations: boolean;
}

export function inputParts(level: Level, results: boolean): InputParts {
  const none: InputParts = {
    volumes: false,
    load: false,
    capacityFactor: false,
    storeEfficiency: false,
    entity: false,
    locations: false,
  };
  switch (level.kind) {
    case "all-entities":
    case "location":
    case "bus":
      return { ...none, volumes: true, load: true };
    case "all-locations":
      return { ...none, volumes: true, load: true, locations: true };
    case "entity":
      return { ...none, volumes: true, load: true, entity: true };
    case "component":
    case "carrier": {
      const ctype = level.ctype;
      return {
        ...none,
        volumes: ctype === "Store" || ctype === "StorageUnit" || ctype === "Line",
        load: ctype === "Load",
        capacityFactor: ctype === "Generator" && !results,
        storeEfficiency: ctype === "Store",
      };
    }
  }
}

/** The level's entities whether active in the period or not (for "not active"), at the selected locations. */
function levelAllSql(scope: LevelQueryScope): string {
  const f = levelFilter(scope.level);
  const conditions = ["true"];
  const literal = (value: string) => sqlString(value);
  if (f.ctype !== null) conditions.push(`ctype = ${literal(f.ctype)}`);
  if (f.carrier !== null) conditions.push(`carrier IS NOT DISTINCT FROM ${literal(f.carrier)}`);
  if (f.location !== null) conditions.push(`list_contains(locations, ${literal(f.location)})`);
  if (f.bus !== null) conditions.push(`list_contains(buses, ${literal(f.bus)})`);
  if (f.entity !== null) conditions.push(`entity = ${literal(f.entity)}`);
  const locations = scope.locations ?? [];
  if (locations.length > 0)
    conditions.push(`list_has_any(locations, [${locations.map(sqlString).join(", ")}])`);
  return `SELECT * FROM entities WHERE ${conditions.join(" AND ")}`;
}

/** CTEs shared by both queries: the window's weights and the hours the window and the period stand for. */
function hoursCtes(scope: LevelQueryScope): string {
  const weighting = serverName("attributes.snapshot_weighting_generators");
  return `
    weights AS (
      SELECT s.snapshot, coalesce(w.value, 1) AS w
      FROM span s LEFT JOIN ${weighting} w ON w.snapshot = s.snapshot
    ),
    hours AS (
      SELECT (SELECT coalesce(sum(w), 0) FROM weights) AS span_hours,
             (SELECT sum(coalesce(w.value, 1)) FROM ${serverName("dims.snapshot")} d
                LEFT JOIN ${weighting} w ON w.snapshot = d.snapshot
              WHERE ${spanCondition("d.snapshot", scope.period, null)}) AS period_hours
    )`;
}

const json = (expression: string) => `to_json(${expression})::VARCHAR`;

/** The inputs query: counts, capacity by type and carrier, and the parts `parts` asks for. */
export function inputsSql(scope: LevelQueryScope, parts: InputParts): string {
  const summary = serverName("manta.attribute_summary");
  const span = (column: string) => spanCondition(column, scope.period, scope.timeWindow);
  const ctes = [
    levelCtes(scope),
    `level_all AS (${levelAllSql(scope)})`,
    // asset_status is optional in a record: read through JSON so a record without it reads NULL.
    `status AS (SELECT entity, json_extract_string(to_json(p), '$.asset_status') AS status FROM ${serverName("properties.entity")} p)`,
    hoursCtes(scope),
  ];
  const columns = [
    `(SELECT ${json("h")} FROM hours h) AS hours`,
    `(SELECT ${json(`{
        active: count(*) FILTER (WHERE l.in_period),
        not_active: count(*) FILTER (WHERE NOT l.in_period),
        existing: count(*) FILTER (WHERE l.in_period AND s.status IN ('existing', 'estimate')),
        candidate: count(*) FILTER (WHERE l.in_period AND s.status = 'candidate'),
        with_status: count(*) FILTER (WHERE l.in_period AND s.status IS NOT NULL)
      }`)} FROM level_all l LEFT JOIN status s USING (entity)) AS counts`,
    `(SELECT ${json("coalesce(list(g ORDER BY g.capacity DESC NULLS LAST), [])")} FROM (
        SELECT m.ctype, m.carrier, any_value(c.color) AS color, any_value(c.nice_name) AS name,
               count(*) AS entities,
               count(*) FILTER (WHERE s.status IN ('existing', 'estimate')) AS existing,
               count(*) FILTER (WHERE s.status = 'candidate') AS candidate,
               sum(m.capacity) AS capacity,
               sum(coalesce(m.capacity_opt, m.capacity)) AS actual,
               sum(greatest(coalesce(m.capacity_opt, m.capacity) - m.capacity, 0)) AS new_build,
               arg_max(m.entity, m.capacity) AS largest, max(m.capacity) AS largest_capacity,
               arg_max(m.entity, coalesce(m.capacity_opt, m.capacity)) AS largest_actual,
               max(coalesce(m.capacity_opt, m.capacity)) AS largest_actual_capacity
        FROM members m
        LEFT JOIN status s USING (entity)
        LEFT JOIN ${serverName("properties.carrier")} c ON c.carrier = m.carrier
        GROUP BY m.ctype, m.carrier
      ) g) AS groups`,
  ];

  if (parts.volumes || parts.entity) {
    ctes.push(`
      attrs AS (
        SELECT label AS entity,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute = 'max_hours') AS max_hours,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute = 'length') AS length,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute = 'efficiency_store') AS efficiency_store,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute = 'efficiency_dispatch') AS efficiency_dispatch
        FROM ${summary} JOIN members m ON m.entity = label
        WHERE dim = 'entity' AND attribute IN ('max_hours', 'length', 'efficiency_store', 'efficiency_dispatch')
        GROUP BY label
      ),
      bus_kv AS (
        SELECT label AS bus, max(TRY_CAST(constant AS DOUBLE)) AS kv
        FROM ${summary} WHERE dim = 'bus' AND attribute = 'v_nom' GROUP BY label
      ),
      sized AS (
        SELECT m.entity, m.ctype, m.capacity, coalesce(m.capacity_opt, m.capacity) AS actual,
               a.max_hours, a.length, a.efficiency_store, a.efficiency_dispatch, k.kv
        FROM members m LEFT JOIN attrs a USING (entity) LEFT JOIN bus_kv k ON k.bus = m.bus
      )`);
    columns.push(
      `(SELECT ${json(`{
        stores: count(*) FILTER (WHERE ctype IN ('Store', 'StorageUnit')),
        storage: sum(CASE ctype WHEN 'Store' THEN capacity WHEN 'StorageUnit' THEN capacity * coalesce(max_hours, 1) END),
        storage_actual: sum(CASE ctype WHEN 'Store' THEN actual WHEN 'StorageUnit' THEN actual * coalesce(max_hours, 1) END),
        lines: count(*) FILTER (WHERE ctype = 'Line'),
        transmission: sum(capacity * length) FILTER (WHERE ctype = 'Line'),
        transmission_actual: sum(actual * length) FILTER (WHERE ctype = 'Line'),
        lines_without_length: count(*) FILTER (WHERE ctype = 'Line' AND length IS NULL),
        kv: list(DISTINCT kv ORDER BY kv DESC) FILTER (WHERE ctype = 'Line' AND kv IS NOT NULL),
        unit_efficiency: coalesce(
          sum(coalesce(efficiency_store, 1) * coalesce(efficiency_dispatch, 1) * capacity)
            FILTER (WHERE ctype = 'StorageUnit' AND (efficiency_store IS NOT NULL OR efficiency_dispatch IS NOT NULL))
            / nullif(sum(capacity) FILTER (WHERE ctype = 'StorageUnit' AND (efficiency_store IS NOT NULL OR efficiency_dispatch IS NOT NULL)), 0),
          avg(coalesce(efficiency_store, 1) * coalesce(efficiency_dispatch, 1))
            FILTER (WHERE ctype = 'StorageUnit' AND (efficiency_store IS NOT NULL OR efficiency_dispatch IS NOT NULL)))
      }`)} FROM sized) AS volumes`,
    );
  }

  if (parts.entity) {
    columns.push(`(SELECT ${json(`{
        entity: m.entity, ctype: m.ctype, carrier: m.carrier, name: c.nice_name, color: c.color,
        bus: m.bus, location: m.location, location1: m.location1,
        cap_attribute: m.cap_attribute, capacity: m.capacity, capacity_opt: m.capacity_opt, status: st.status,
        max_hours: z.max_hours, length: z.length
      }`)} FROM members m
        LEFT JOIN sized z USING (entity)
        LEFT JOIN status st USING (entity)
        LEFT JOIN ${serverName("properties.carrier")} c ON c.carrier = m.carrier
        LIMIT 1) AS entity`);
  }

  if (parts.load) {
    const pSet = serverName("attributes.p_set");
    ctes.push(`
      loads AS (SELECT entity FROM members WHERE ctype = 'Load'),
      load_points AS (
        SELECT a.entity, a.snapshot, a.value FROM ${pSet} a JOIN loads USING (entity)
        WHERE a.snapshot IS NOT NULL AND ${span("a.snapshot")}
        UNION ALL
        SELECT a.entity, s.snapshot, a.value FROM ${pSet} a JOIN loads USING (entity) CROSS JOIN span s
        WHERE a.snapshot IS NULL
      ),
      load_weighted AS (SELECT p.entity, p.snapshot, p.value, w.w FROM load_points p JOIN weights w ON w.snapshot = p.snapshot),
      load_total AS (SELECT snapshot, any_value(w) AS w, sum(value) AS value FROM load_weighted GROUP BY snapshot),
      load_each AS (SELECT entity, max(value) AS peak, sum(value * w) / nullif(sum(w), 0) AS mean FROM load_weighted GROUP BY entity)`);
    columns.push(
      `(SELECT ${json(`{
        loads: (SELECT count(*) FROM loads),
        peak: max(value),
        mean: sum(value * w) / nullif(sum(w), 0),
        largest: (SELECT arg_max(entity, mean) FROM load_each),
        largest_mean: (SELECT max(mean) FROM load_each),
        largest_peak: (SELECT arg_max(peak, mean) FROM load_each)
      }`)} FROM load_total) AS load`,
    );
  }

  if (parts.capacityFactor) {
    const pMaxPu = serverName("attributes.p_max_pu");
    ctes.push(`
      gens AS (SELECT entity, capacity FROM members WHERE ctype = 'Generator'),
      pu_mean AS (
        SELECT entity, any_value(mean_pu) AS mean_pu FROM (
          SELECT a.entity, sum(a.value * w.w) / nullif(sum(w.w), 0) AS mean_pu
          FROM ${pMaxPu} a JOIN gens g USING (entity) JOIN weights w ON w.snapshot = a.snapshot
          WHERE a.snapshot IS NOT NULL AND ${span("a.snapshot")}
          GROUP BY a.entity
          UNION ALL
          SELECT a.entity, any_value(a.value) FROM ${pMaxPu} a JOIN gens g USING (entity)
          WHERE a.snapshot IS NULL GROUP BY a.entity
        ) GROUP BY entity
      )`);
    columns.push(
      `(SELECT ${json(`{
        estimate: sum(g.capacity * coalesce(p.mean_pu, 1)) / nullif(sum(g.capacity), 0),
        with_profile: count(p.mean_pu),
        generators: count(*)
      }`)} FROM gens g LEFT JOIN pu_mean p USING (entity)) AS capacity_factor`,
    );
  }

  if (parts.storeEfficiency) {
    // A store's round trip: the links into its bus (charging) times the links out of it (discharging), each capacity-weighted.
    ctes.push(`
      store_buses AS (SELECT DISTINCT bus FROM members WHERE ctype = 'Store'),
      link_efficiency AS (
        SELECT l.entity, l.bus, l.bus1, l.capacity, TRY_CAST(a.constant AS DOUBLE) AS efficiency
        FROM entities l
        JOIN ${summary} a ON a.dim = 'entity' AND a.label = l.entity AND a.attribute = 'efficiency' AND a.bus = l.bus1
        WHERE l.ctype = 'Link' AND l.in_period AND a.constant IS NOT NULL
      )`);
    const mean = (end: string) =>
      `(SELECT coalesce(sum(l.efficiency * l.capacity) / nullif(sum(l.capacity), 0), avg(l.efficiency)) FROM link_efficiency l JOIN store_buses b ON b.bus = l.${end})`;
    columns.push(
      `${json(`{
        charge: ${mean("bus1")},
        discharge: ${mean("bus")}
      }`)} AS store_efficiency`,
    );
  }

  if (parts.locations) {
    const real = `SELECT bus, carrier, location FROM ${serverName("manta.bus_location")} WHERE NOT virtual`;
    columns.push(`(SELECT count(*) FROM ${serverName("manta.locations")}) AS location_count`);
    columns.push(`(SELECT ${json("coalesce(list({carrier: carrier, buses: buses} ORDER BY buses DESC, carrier), [])")} FROM (
        SELECT carrier, count(*) AS buses FROM (${real}) GROUP BY carrier)) AS buses`);
    // The zone level that groups the locations into the fewest regions, more than one.
    columns.push(`(SELECT ${json("{level: level, zones: zones}")} FROM (
        SELECT level, count(DISTINCT zone) AS zones FROM ${serverName("manta.location_zones")}
        WHERE level IS NOT NULL GROUP BY level HAVING count(DISTINCT zone) > 1
        ORDER BY zones, level LIMIT 1)) AS regions`);
  }

  return `WITH ${ctes.join(",\n")}\nSELECT ${columns.join(",\n")}`;
}

/** Which parts of the result query a level needs. */
export interface ResultParts {
  /** Generation, curtailment and market value (5.6). */
  generators: boolean;
  /** Mean state of charge of stores. */
  stores: boolean;
}

export function resultParts(level: Level): ResultParts | null {
  switch (level.kind) {
    case "component":
    case "carrier":
      return { generators: level.ctype === "Generator", stores: level.ctype === "Store" };
    case "entity":
      // An entity's tiles need only its flow.
      return { generators: false, stores: false };
    default:
      return null;
  }
}

/**
 * The run result query: per type, the flow at each member's first bus summed
 * over the window's weighted hours (out, in and both ways), and the parts
 * `parts` asks for.
 */
export function resultsSql(scope: LevelQueryScope, parts: ResultParts): string {
  const span = (column: string) => spanCondition(column, scope.period, scope.timeWindow);
  const p = serverName("attributes.p");
  const ctes = [
    levelCtes(scope),
    hoursCtes(scope),
    `flows AS (
      SELECT m.ctype, a.value AS v, w.w
      FROM ${p} a
      JOIN members m ON m.entity = a.connection.entity AND m.bus = a.connection.bus
      JOIN weights w ON w.snapshot = a.snapshot
      WHERE m.ctype <> 'Load' AND ${span("a.snapshot")}
    )`,
  ];
  const columns = [
    `(SELECT ${json("h")} FROM hours h) AS hours`,
    `(SELECT ${json("coalesce(list(f), [])")} FROM (
        SELECT ctype, sum(v * w) AS net, sum(greatest(v, 0) * w) AS out, sum(greatest(-v, 0) * w) AS "in", sum(abs(v) * w) AS both_ways
        FROM flows GROUP BY ctype) f) AS flows`,
  ];

  if (parts.generators) {
    const pMaxPu = serverName("attributes.p_max_pu");
    ctes.push(`
      g AS (SELECT entity, bus, coalesce(capacity_opt, capacity) AS cap FROM members WHERE ctype = 'Generator'),
      gp AS (
        SELECT a.connection.entity AS entity, a.snapshot, a.value FROM ${p} a JOIN g ON g.entity = a.connection.entity
        WHERE ${span("a.snapshot")}
      ),
      pms AS (
        SELECT a.entity, a.snapshot, a.value FROM ${pMaxPu} a JOIN g USING (entity)
        WHERE a.snapshot IS NOT NULL AND ${span("a.snapshot")}
      ),
      pmc AS (SELECT a.entity, any_value(a.value) AS value FROM ${pMaxPu} a JOIN g USING (entity) WHERE a.snapshot IS NULL GROUP BY a.entity),
      gx AS (
        SELECT g.cap, coalesce(gp.value, 0) AS p, coalesce(pms.value, pmc.value, 1) AS pu,
               pms.value IS NOT NULL AS variable, pr.value AS price, w.w
        FROM g
        CROSS JOIN weights w
        LEFT JOIN gp ON gp.entity = g.entity AND gp.snapshot = w.snapshot
        LEFT JOIN pms ON pms.entity = g.entity AND pms.snapshot = w.snapshot
        LEFT JOIN pmc ON pmc.entity = g.entity
        LEFT JOIN ${serverName("attributes.marginal_price")} pr ON pr.bus = g.bus AND pr.snapshot = w.snapshot
      )`);
    columns.push(
      `(SELECT ${json(`{
        generation: sum(p * w),
        available: sum(cap * pu * w) FILTER (WHERE variable),
        curtailed: sum((cap * pu - p) * w) FILTER (WHERE variable),
        market_value: sum(p * price * w) FILTER (WHERE price IS NOT NULL) / nullif(sum(p * w) FILTER (WHERE price IS NOT NULL), 0),
        mean_price: sum(price * w) / nullif(sum(w) FILTER (WHERE price IS NOT NULL), 0)
      }`)} FROM gx) AS generators`,
    );
  }

  if (parts.stores) {
    columns.push(`(SELECT ${json("{energy: sum(a.value * w.w)}")}
        FROM ${serverName("attributes.e")} a
        JOIN members m ON m.entity = a.entity AND m.ctype = 'Store'
        JOIN weights w ON w.snapshot = a.snapshot
        WHERE ${span("a.snapshot")}) AS stores`);
  }

  return `WITH ${ctes.join(",\n")}\nSELECT ${columns.join(",\n")}`;
}
