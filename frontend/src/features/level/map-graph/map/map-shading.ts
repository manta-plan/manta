// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useShownData } from "../../../project/lib/record-data";
import { serverName, serverQuery } from "../../../project/lib/record-server/client";
import { levelCtes, scopeKey, type LevelQueryScope } from "../../level-sql";
import { baseScope } from "../map-graph-data";
import type { LineColouring, RegionShading } from "./map-layer-store";

// The values the map colours by: one per location (region shading) or per
// Line (line colouring), over the period and time window. On Inspect a
// capacity is the optimised one where the solve set it. Energy is weighted
// by snapshot_weighting_generators and a constant p_set counts for every
// snapshot, as elsewhere in the app.

export interface LayerValues {
  values: Map<string, number>;
  unit: string;
  /** How a value reads: a share (0–1) shows as a percentage. */
  percent: boolean;
}

const w = () => serverName("attributes.snapshot_weighting_generators");
const inSpan = (column: string) => `${column} IN (SELECT snapshot FROM span)`;

/** Capacity at the stage: optimised on Inspect where set. */
const cap = (withResults: boolean) =>
  withResults ? "coalesce(e.capacity_opt, e.capacity)" : "e.capacity";

const maxHours = () =>
  `LEFT JOIN ${serverName("manta.attribute_summary")} mh ON mh.dim = 'entity' AND mh.label = e.entity AND mh.attribute = 'max_hours' AND mh.bus IS NULL`;
const volume = (capacity: string) =>
  `CASE e.ctype WHEN 'Store' THEN ${capacity} WHEN 'StorageUnit' THEN ${capacity} * coalesce(TRY_CAST(mh.constant AS DOUBLE), 1) END`;

export function regionSql(
  shading: RegionShading,
  withResults: boolean,
): { sql: string; unit: string; percent: boolean } {
  const c = cap(withResults);
  const opt = withResults ? ", optimised" : "";
  switch (shading) {
    case "generator-capacity":
      return {
        sql: `SELECT e.location, sum(${c}) AS value FROM entities e WHERE e.in_period AND e.ctype = 'Generator' AND e.location IS NOT NULL GROUP BY 1`,
        unit: `MW${opt}`,
        percent: false,
      };
    case "link-capacity":
      return {
        sql: `SELECT e.location, sum(${c}) AS value FROM entities e WHERE e.in_period AND e.ctype = 'Link' AND e.location IS NOT NULL GROUP BY 1`,
        unit: `MW${opt}`,
        percent: false,
      };
    case "storage-volume":
      return {
        sql: `SELECT e.location, sum(${volume(c)}) / 1e3 AS value FROM entities e ${maxHours()} WHERE e.in_period AND e.ctype IN ('Store', 'StorageUnit') AND e.location IS NOT NULL GROUP BY 1`,
        unit: `GWh${opt}`,
        percent: false,
      };
    case "load-peak":
    case "load-demand": {
      const pSet = serverName("attributes.p_set");
      const demand = `
        SELECT d.location, d.snapshot, sum(d.value) AS value FROM (
          SELECT e.location, a.snapshot, a.value FROM ${pSet} a JOIN entities e ON e.entity = a.entity AND e.in_period AND e.ctype = 'Load' WHERE ${inSpan("a.snapshot")}
          UNION ALL
          SELECT e.location, s.snapshot, a.value FROM ${pSet} a JOIN entities e ON e.entity = a.entity AND e.in_period AND e.ctype = 'Load' CROSS JOIN span s WHERE a.snapshot IS NULL
        ) d WHERE d.location IS NOT NULL GROUP BY ALL`;
      return shading === "load-peak"
        ? {
            sql: `SELECT location, max(value) AS value FROM (${demand}) GROUP BY 1`,
            unit: "MW, peak of p_set",
            percent: false,
          }
        : {
            sql: `SELECT d.location, sum(d.value * coalesce(wt.value, 1)) / 1e6 AS value FROM (${demand}) d LEFT JOIN ${w()} wt ON wt.snapshot = d.snapshot GROUP BY 1`,
            unit: "TWh",
            percent: false,
          };
    }
    case "generator-utilisation":
      return {
        sql: `
          SELECT e.location, sum(a.value * coalesce(wt.value, 1)) / nullif(sum(coalesce(e.capacity_opt, e.capacity) * coalesce(wt.value, 1)), 0) AS value
          FROM ${serverName("attributes.p")} a
          JOIN entities e ON e.entity = a.connection.entity AND e.in_period AND e.ctype = 'Generator'
          LEFT JOIN ${w()} wt ON wt.snapshot = a.snapshot
          WHERE ${inSpan("a.snapshot")} AND e.location IS NOT NULL
          GROUP BY 1`,
        unit: "capacity factor",
        percent: true,
      };
    case "link-utilisation":
      return {
        sql: `
          SELECT e.location, sum(abs(a.value) * coalesce(wt.value, 1)) / nullif(sum(coalesce(e.capacity_opt, e.capacity) * coalesce(wt.value, 1)), 0) AS value
          FROM ${serverName("properties.connection")} c
          JOIN entities e ON e.entity = c.connection.entity AND e.in_period AND e.ctype = 'Link'
          JOIN ${serverName("attributes.p")} a ON a.connection = c.connection
          LEFT JOIN ${w()} wt ON wt.snapshot = a.snapshot
          WHERE c.role = 'input' AND ${inSpan("a.snapshot")} AND e.location IS NOT NULL
          GROUP BY 1`,
        unit: "mean |p0| ÷ p_nom_opt",
        percent: true,
      };
    case "storage-utilisation": {
      const level = (attribute: string, ctype: string) => `
        SELECT a.entity, avg(a.value) AS level FROM ${serverName(`attributes.${attribute}`)} a
        JOIN entities e ON e.entity = a.entity AND e.in_period AND e.ctype = '${ctype}'
        WHERE ${inSpan("a.snapshot")} GROUP BY 1`;
      return {
        sql: `
          SELECT e.location, sum(l.level) / nullif(sum(${volume("coalesce(e.capacity_opt, e.capacity)")}), 0) AS value
          FROM (${level("e", "Store")} UNION ALL ${level("state_of_charge", "StorageUnit")}) l
          JOIN entities e USING (entity) ${maxHours()}
          WHERE e.location IS NOT NULL
          GROUP BY 1`,
        unit: "mean state of charge",
        percent: true,
      };
    }
    case "bus-price": {
      const buses = serverName("manta.bus_location");
      return {
        // The location's own bus (named after it), weighted by the hours each snapshot stands for.
        sql: `
          SELECT b.location, sum(m.value * coalesce(wt.value, 1)) / sum(coalesce(wt.value, 1)) AS value
          FROM ${serverName("attributes.marginal_price")} m
          JOIN ${buses} b ON b.bus = m.bus AND b.bus = b.location AND NOT b.virtual
          LEFT JOIN ${w()} wt ON wt.snapshot = m.snapshot
          WHERE ${inSpan("m.snapshot")}
          GROUP BY 1`,
        unit: "€/MWh, mean marginal_price",
        percent: false,
      };
    }
  }
}

export function lineSql(
  colouring: LineColouring,
  withResults: boolean,
): { sql: string; unit: string; percent: boolean } {
  if (colouring === "capacity") {
    return {
      sql: `SELECT e.entity AS key, ${cap(withResults)} AS value FROM entities e WHERE e.in_period AND e.ctype = 'Line'`,
      unit: withResults ? "MVA, optimised" : "MVA",
      percent: false,
    };
  }
  return {
    sql: `
      SELECT e.entity AS key, avg(abs(a.value)) / nullif(coalesce(e.capacity_opt, e.capacity), 0) AS value
      FROM entities e
      JOIN ${serverName("properties.connection")} c ON c.connection.entity = e.entity AND c.role = 'input'
      JOIN ${serverName("attributes.p")} a ON a.connection = c.connection AND ${inSpan("a.snapshot")}
      WHERE e.ctype = 'Line' AND e.in_period
      GROUP BY e.entity, e.capacity, e.capacity_opt`,
    unit: "mean |p0| ÷ s_nom_opt",
    percent: true,
  };
}

async function loadValues(
  scope: LevelQueryScope,
  query: { sql: string; unit: string; percent: boolean },
  keyColumn: string,
): Promise<LayerValues> {
  const rows = await serverQuery<Record<string, unknown>>(
    `WITH ${levelCtes(scope)} SELECT * FROM (${query.sql}) q`,
  );
  const values = new Map<string, number>();
  for (const row of rows) {
    const value = Number(row.value);
    if (row.value !== null && Number.isFinite(value)) values.set(String(row[keyColumn]), value);
  }
  return { values, unit: query.unit, percent: query.percent };
}

/** Each location's value for the region shading chosen; null when it's off. */
export function useRegionShading(
  scope: LevelQueryScope | null,
  shading: RegionShading | null,
  withResults: boolean,
) {
  const base = scope && baseScope(scope);
  return useShownData(
    "side-shading",
    base && shading ? [scopeKey(base), shading, withResults] : null,
    () => loadValues(base!, regionSql(shading!, withResults), "location"),
  );
}

/** Each Line's value for the colouring chosen; null when it's off. */
export function useLineColouring(
  scope: LevelQueryScope | null,
  colouring: LineColouring | null,
  withResults: boolean,
) {
  const base = scope && baseScope(scope);
  return useShownData(
    "side-line-colour",
    base && colouring ? [scopeKey(base), colouring, withResults] : null,
    () => loadValues(base!, lineSql(colouring!, withResults), "key"),
  );
}
