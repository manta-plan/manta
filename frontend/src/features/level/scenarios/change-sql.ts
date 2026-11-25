// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { DraftChange, DraftChangeTarget } from "../../project/lib/draft-scenarios";
import { serverName, serverQuery, sqlString } from "../../project/lib/record-server/client";
import { entitiesSql } from "../level-sql";

// Reads for draft changes, in the shown catalog (the draft's parent when a
// draft is shown). Matches count the entities active in the shown period, as
// the level pages do (SQL doc 10.2 to 10.4, over `entities`).

type FilterTarget = Extract<DraftChangeTarget, { kind: "filter" }>;

const literal = (value: string | null) => (value === null ? "NULL::VARCHAR" : sqlString(value));

/** A condition on an `entities` row (alias e) for a filter target. */
function matchCondition(target: FilterTarget): string {
  const conditions = ["e.in_period", `e.ctype = ${sqlString(target.ctype)}`];
  if (target.carrier !== null) conditions.push(`e.carrier = ${sqlString(target.carrier)}`);
  if (target.location !== null)
    conditions.push(`list_contains(e.locations, ${sqlString(target.location)})`);
  return conditions.join(" AND ");
}

export interface MatchAttribute {
  attribute: string;
  /** Matching entities that store it (others take the default). */
  entities: number;
  /** Of those, how many hold a time series. */
  withSeries: number;
}

export interface Matches {
  matching: number;
  attributes: MatchAttribute[];
}

/** 10.3: how many entities a filter matches, and the numeric or series attributes they store. */
export async function loadMatches(target: FilterTarget, period: string): Promise<Matches> {
  const rows = await serverQuery<{
    matching: number;
    attribute: string | null;
    entities: number | null;
    withSeries: number | null;
  }>(`
    WITH entities AS (${entitiesSql(period)}),
    members AS (SELECT e.entity FROM entities e WHERE ${matchCondition(target)}),
    attrs AS (
      SELECT s.attribute, count(DISTINCT s.label)::INTEGER AS entities,
             (count(DISTINCT s.label) FILTER (WHERE s.series_rows > 0))::INTEGER AS "withSeries"
      FROM members m
      JOIN ${serverName("manta.attribute_summary")} s ON s.dim = 'entity' AND s.label = m.entity AND s.bus IS NULL
      WHERE TRY_CAST(s.constant AS DOUBLE) IS NOT NULL OR s.series_rows > 0
      GROUP BY s.attribute
    )
    SELECT (SELECT count(*) FROM members)::INTEGER AS matching, a.attribute, a.entities, a."withSeries"
    FROM (SELECT 1) one LEFT JOIN attrs a ON true
    ORDER BY a.attribute`);
  return {
    matching: rows[0]?.matching ?? 0,
    attributes: rows
      .filter((row) => row.attribute !== null)
      .map((row) => ({
        attribute: row.attribute!,
        entities: row.entities ?? 0,
        withSeries: row.withSeries ?? 0,
      })),
  };
}

/** One entity's stored value of an attribute: a constant, or a series' row count. */
export interface StoredValue {
  value: number | null;
  seriesRows: number;
}

export interface DraftFigures {
  /** Per filter change id: the entities it matches. */
  matches: Record<string, number>;
  /** Per `${entity}\n${attribute}` of a single-entity change: its stored value before the draft. */
  values: Record<string, StoredValue>;
}

export const valueKey = (entity: string, attribute: string) => `${entity}\n${attribute}`;

/** 10.2 for a draft: each filter change's matched count, and each single-entity change's value before. */
export async function loadDraftFigures(
  changes: DraftChange[],
  period: string,
): Promise<DraftFigures> {
  const filters = changes.flatMap((change) =>
    change.kind === "attribute" && change.target.kind === "filter"
      ? [{ id: change.id, target: change.target }]
      : [],
  );
  const singles = changes.flatMap((change) =>
    change.kind === "attribute" && change.target.kind === "entity"
      ? [{ entity: change.target.entity, attribute: change.attribute }]
      : [],
  );
  const [counted, stored] = await Promise.all([
    filters.length === 0
      ? Promise.resolve([])
      : serverQuery<{ id: string; n: number }>(`
          WITH entities AS (${entitiesSql(period)}),
          t(id, ctype, carrier, location) AS (VALUES ${filters.map(({ id, target }) => `(${sqlString(id)}, ${sqlString(target.ctype)}, ${literal(target.carrier)}, ${literal(target.location)})`).join(", ")})
          SELECT t.id, count(e.entity)::INTEGER AS n
          FROM t LEFT JOIN entities e
            ON e.in_period AND e.ctype = t.ctype
           AND (t.carrier IS NULL OR e.carrier = t.carrier)
           AND (t.location IS NULL OR list_contains(e.locations, t.location))
          GROUP BY t.id`),
    singles.length === 0
      ? Promise.resolve([])
      : serverQuery<{
          entity: string;
          attribute: string;
          value: number | null;
          seriesRows: number;
        }>(`
          WITH t(entity, attribute) AS (VALUES ${singles.map((item) => `(${sqlString(item.entity)}, ${sqlString(item.attribute)})`).join(", ")})
          SELECT s.label AS entity, s.attribute, TRY_CAST(s.constant AS DOUBLE) AS value, s.series_rows::INTEGER AS "seriesRows"
          FROM ${serverName("manta.attribute_summary")} s
          JOIN t ON s.label = t.entity AND s.attribute = t.attribute
          WHERE s.dim = 'entity' AND s.bus IS NULL`),
  ]);
  return {
    matches: Object.fromEntries(counted.map((row) => [row.id, row.n])),
    values: Object.fromEntries(
      stored.map((row) => [
        valueKey(row.entity, row.attribute),
        { value: row.value, seriesRows: row.seriesRows },
      ]),
    ),
  };
}

/** An entity's type, carrier and location: what a single-entity change records. */
export async function loadEntityPlace(
  entity: string,
): Promise<{ ctype: string; carrier: string | null; location: string | null } | null> {
  const rows = await serverQuery<{
    ctype: string;
    carrier: string | null;
    location: string | null;
  }>(`
    SELECT e.ctype, e.carrier, coalesce(a.location, b.location0) AS location
    FROM ${serverName("properties.entity")} e
    LEFT JOIN ${serverName("manta.attached")} a USING (entity)
    LEFT JOIN (SELECT entity, any_value(location0) AS location0 FROM ${serverName("manta.branches")} GROUP BY entity) b USING (entity)
    WHERE e.entity = ${sqlString(entity)}
    LIMIT 1`);
  return rows[0] ?? null;
}
