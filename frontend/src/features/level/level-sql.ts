// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { serverName, sqlString } from "../project/lib/record-server/client";
import { levelFilter, type Level } from "./level";
import type { TimeWindow } from "./level-store";

// The shared SQL fragments every level query starts from (see the handover's
// SQL tab, "Shared fragments"): CTEs to put after WITH.
//
//   entities     each entity once: bus(es), location(s), capacity attribute
//                and value, optimised capacity, and whether it's active in
//                the period (build_year ≤ Y < build_year + lifetime; without
//                both it always is)
//   members      the active entities at the level, and at the selected
//                locations when any are selected
//   span         the period's snapshots inside the time window
//
// Every relation is in the shown catalog (serverName). Values are written in
// with sqlString / numbers, never interpolated raw.

export interface LevelQueryScope {
  level: Level;
  /** The investment period (a snapshot period, as text). */
  period: string;
  /** The time window; null is the period's full span. */
  timeWindow: TimeWindow | null;
  /** Locations selected on the map; empty is all. */
  locations?: readonly string[];
}

const literal = (value: string | null) => (value === null ? "NULL::VARCHAR" : sqlString(value));

/** The period as a number for build_year arithmetic; a period that isn't one (a label) makes every entity active. */
function periodNumber(period: string): string {
  const value = Number(period);
  return Number.isFinite(value) ? String(value) : "NULL::DOUBLE";
}

/** The `entities` CTE body. */
export function entitiesSql(period: string): string {
  const y = periodNumber(period);
  return `
    SELECT e.entity, e.ctype, e.carrier,
           coalesce(a.bus, b.bus0) AS bus,
           coalesce(a.location, b.location0) AS location,
           b.bus1, b.location1,
           list_filter(list_distinct([coalesce(a.bus, b.bus0)] || coalesce(b.outputs, [])), lambda x: x IS NOT NULL) AS buses,
           list_filter(list_distinct([coalesce(a.location, b.location0)] || coalesce(b.output_locations, [])), lambda x: x IS NOT NULL) AS locations,
           CASE e.ctype WHEN 'Store' THEN 'e_nom' WHEN 'Line' THEN 's_nom' WHEN 'Transformer' THEN 's_nom'
                        WHEN 'Load' THEN NULL WHEN 'GlobalConstraint' THEN NULL ELSE 'p_nom' END AS cap_attribute,
           CASE WHEN e.ctype NOT IN ('Load', 'GlobalConstraint') THEN coalesce(s.capacity, 0) END AS capacity,
           s.capacity_opt,
           coalesce(s.build_year, 0) AS build_year,
           coalesce(s.lifetime, 'inf'::DOUBLE) AS lifetime,
           coalesce(${y} IS NULL OR (coalesce(s.build_year, 0) <= ${y} AND ${y} < coalesce(s.build_year, 0) + coalesce(s.lifetime, 'inf'::DOUBLE)), true)
             AND coalesce(s.active, true) AS in_period
    FROM ${serverName("properties.entity")} e
    LEFT JOIN ${serverName("manta.attached")} a USING (entity)
    LEFT JOIN (
        SELECT entity, any_value(bus0) AS bus0, any_value(location0) AS location0,
               min(bus1) AS bus1, min(location1) AS location1,
               list(DISTINCT bus1 ORDER BY bus1) AS outputs,
               list(DISTINCT location1 ORDER BY location1) AS output_locations
        FROM ${serverName("manta.branches")} GROUP BY entity
    ) b USING (entity)
    LEFT JOIN (
        SELECT label AS entity,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute IN ('p_nom', 's_nom', 'e_nom')) AS capacity,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute IN ('p_nom_opt', 's_nom_opt', 'e_nom_opt')) AS capacity_opt,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute = 'build_year') AS build_year,
               max(TRY_CAST(constant AS DOUBLE)) FILTER (WHERE attribute = 'lifetime') AS lifetime,
               bool_and(TRY_CAST(constant AS BOOLEAN)) FILTER (WHERE attribute = 'active') AS active
        FROM ${serverName("manta.attribute_summary")}
        WHERE dim = 'entity' AND bus IS NULL
          AND attribute IN ('p_nom', 's_nom', 'e_nom', 'p_nom_opt', 's_nom_opt', 'e_nom_opt', 'build_year', 'lifetime', 'active')
        GROUP BY label
    ) s USING (entity)`;
}

/** The `members` CTE body (needs `entities`). */
export function membersSql(level: Level, locations: readonly string[] = []): string {
  const f = levelFilter(level);
  const conditions = ["in_period"];
  if (f.ctype !== null) conditions.push(`ctype = ${literal(f.ctype)}`);
  if (f.carrier !== null) conditions.push(`carrier IS NOT DISTINCT FROM ${literal(f.carrier)}`);
  if (f.location !== null) conditions.push(`list_contains(locations, ${literal(f.location)})`);
  if (f.bus !== null) conditions.push(`list_contains(buses, ${literal(f.bus)})`);
  if (f.entity !== null) conditions.push(`entity = ${literal(f.entity)}`);
  if (locations.length > 0)
    conditions.push(`list_has_any(locations, [${locations.map(sqlString).join(", ")}])`);
  return `SELECT * FROM entities WHERE ${conditions.join(" AND ")}`;
}

/** A condition on a `snapshot` struct column: in the period and the window. */
export function spanCondition(
  column: string,
  period: string,
  timeWindow: TimeWindow | null,
): string {
  const conditions = [`${column}.period::VARCHAR = ${sqlString(period)}`];
  if (timeWindow) {
    conditions.push(`${column}.timestep >= ${sqlString(timeWindow.start)}::TIMESTAMP`);
    conditions.push(`${column}.timestep < ${sqlString(timeWindow.end)}::TIMESTAMP`);
    if (timeWindow.months)
      conditions.push(
        `month(${column}.timestep) IN (${timeWindow.months.map((m) => m + 1).join(", ")})`,
      );
  }
  return conditions.join(" AND ");
}

/** The `span` CTE body: the period's snapshots in the window. */
export function spanSql(period: string, timeWindow: TimeWindow | null): string {
  return `SELECT snapshot FROM ${serverName("dims.snapshot")} WHERE ${spanCondition("snapshot", period, timeWindow)}`;
}

/** `entities AS (…), members AS (…), span AS (…)`: put after WITH, then the query. */
export function levelCtes(scope: LevelQueryScope): string {
  return [
    `entities AS (${entitiesSql(scope.period)})`,
    `members AS (${membersSql(scope.level, scope.locations)})`,
    `span AS (${spanSql(scope.period, scope.timeWindow)})`,
  ].join(",\n");
}

/** A stable cache key part for a time window. */
export function windowKey(timeWindow: TimeWindow | null): (string | null)[] {
  return [
    timeWindow?.start ?? null,
    timeWindow?.end ?? null,
    timeWindow?.months?.join(",") ?? null,
  ];
}

/** A stable cache key part for a scope (SWR args). */
export function scopeKey(scope: LevelQueryScope): string {
  return JSON.stringify([
    scope.level,
    scope.period,
    ...windowKey(scope.timeWindow),
    scope.locations ?? [],
  ]);
}
