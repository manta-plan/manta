// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useProjectStore } from "../../project/store/project-store";
import { isPlaceholderCondition, type Aggregate, type QueryResult } from "./custom-query";
import { CARRIER_GROUPS } from "./inspect-filters";
import { openRecord } from "../../project/lib/record-server/queries";
import { serverQuery, sqlString } from "../../project/lib/record-server/client";
import {
  BUILT_IN_QUERIES,
  compileQuerySql,
  type OutputColumn,
  type ResultQuery,
  type ValueKind,
} from "./result-queries";
import type { InspectResult, QueryRequest, ResultSource, ResultTableInfo } from "./result-source";

// Answers the Analyse page from the record: a widget's query (one aggregate
// of `value`, grouped by up to two columns, under the page filters) is
// compiled to SQL over one of the queries (resultQueries.ts) and runs on the
// server, next to the data. Only the grouped rows travel.

/** Every table widgets can read: the computed ones. */
export function allQueries(): ResultQuery[] {
  return BUILT_IN_QUERIES;
}

/** A query as the widget builder sees it. */
export function queryTableInfo(query: ResultQuery): ResultTableInfo {
  const { name, label, description, unit, valueLabel, columns, kind } = query;
  return {
    name,
    label,
    description,
    unit,
    valueLabel,
    columns,
    kind,
    builtIn: "builtIn" in query && query.builtIn === true,
    defaultAggregate: kind === "price" || kind === "power" ? "avg" : "sum",
  };
}

// ------------------------------------------------------------ Opening results

const opening = new Map<string, Promise<unknown>>();

/** A run result's catalog is attached on the server the first time it's read. */
function ensureOpen(result: InspectResult): Promise<unknown> {
  const info = useProjectStore.getState().record?.info;
  if (!info || info.revisions.find((revision) => revision.name === result.id)?.open)
    return Promise.resolve();
  const key = `${info.id}\n${result.id}`;
  let promise = opening.get(key);
  if (!promise) {
    promise = openRecord(info.id, result.id).catch((error: unknown) => {
      opening.delete(key);
      throw error;
    });
    opening.set(key, promise);
  }
  return promise;
}

// ------------------------------------------------------------ Running SQL

/** Rows of `sql` (plain record names; computed tables by name) for one result. */
export async function runResultSql<T>(result: InspectResult, sql: string): Promise<T[]> {
  await ensureOpen(result);
  return serverQuery<T>(compileQuerySql(sql, result.catalog));
}

/** The columns `sql` returns, and their types, without reading its rows. */
export function describeResultSql(result: InspectResult, sql: string): Promise<OutputColumn[]> {
  return runResultSql<OutputColumn>(
    result,
    `SELECT column_name AS name, column_type AS type FROM (DESCRIBE (\n${sql.trim().replace(/;\s*$/, "")}\n))`,
  );
}

/** Which component types each attribute belongs to, for grouping the raw tables. */
export async function loadAttributeTypes(result: InspectResult): Promise<Map<string, string[]>> {
  const rows = await runResultSql<{ attribute: string; ctypes: string[] }>(
    result,
    "SELECT attribute, list(DISTINCT ctype ORDER BY ctype) AS ctypes FROM manta.ctype_attributes GROUP BY attribute",
  );
  return new Map(rows.map((row) => [row.attribute, Array.from(row.ctypes ?? [])]));
}

/** The record's investment periods, from one result (cached by the caller, through SWR). */
async function loadPeriods(result: InspectResult): Promise<string[]> {
  const rows = await runResultSql<{ period: string }>(
    result,
    "SELECT DISTINCT CAST(snapshot.period AS VARCHAR) AS period FROM dims.snapshot ORDER BY 1",
  );
  return rows.map((row) => row.period);
}

/** A column's labels in one query, for the builder's value pickers (at most 500). */
export async function loadColumnValues(
  result: InspectResult,
  queryName: string,
  column: string,
): Promise<string[]> {
  const name = `"${column.replaceAll('"', '""')}"`;
  const rows = await runResultSql<{ v: string }>(
    result,
    `SELECT DISTINCT CAST(${name} AS VARCHAR) AS v FROM ${queryName} WHERE ${name} IS NOT NULL ORDER BY 1 LIMIT 500`,
  );
  return rows.map((row) => row.v);
}

// ------------------------------------------------------------ Widget queries

const AGGREGATES: Record<Aggregate, string> = { sum: "sum", avg: "avg", max: "max", min: "min" };

/** How a timed query's values combine over places and labels at one snapshot, then over snapshots. */
function timedAggregates(kind: ValueKind, aggregate: Aggregate): { space: string; time: string } {
  const space = kind === "price" ? AGGREGATES[aggregate] : "sum";
  if (aggregate === "avg")
    return { space, time: kind === "energy" ? "avg(v)" : "sum(v * w) / nullif(sum(w), 0)" };
  if (aggregate === "sum") return { space, time: kind === "energy" ? "sum(v)" : "sum(v * w)" };
  return { space, time: `${AGGREGATES[aggregate]}(v)` };
}

/** Whether a carrier label belongs to one of the groups the filter keeps: carrierGroupOf's matching, in SQL. */
function carrierCondition(groups: string[]): string {
  const matches = CARRIER_GROUPS.filter((group) => groups.includes(group.id)).flatMap((group) =>
    group.match.map((match) => match.toLowerCase()),
  );
  return matches.length === 0
    ? "false"
    : `(${matches.map((match) => `starts_with(lower(carrier), ${sqlString(match)})`).join(" OR ")})`;
}

const column = (name: string) => `"${name.replaceAll('"', '""')}"`;

function conditions(request: QueryRequest): string[] {
  const { query, filters } = request;
  return query.where.flatMap((condition): string[] => {
    // A condition with nothing picked yet keeps everything.
    if (!isPlaceholderCondition(condition))
      return condition.values.length === 0
        ? []
        : [
            `CAST(${column(condition.column)} AS VARCHAR) IN (${condition.values.map(sqlString).join(", ")})`,
          ];
    if (condition.placeholder === "buses")
      return filters.buses.length > 0
        ? [`bus IN (${filters.buses.map(sqlString).join(", ")})`]
        : [];
    if (condition.placeholder === "period")
      return filters.period !== null ? [`period = ${sqlString(filters.period)}`] : [];
    return filters.carriers.length > 0 ? [carrierCondition(filters.carriers)] : [];
  });
}

/** How many periods the rows keep: 1 under the period filter, the values a period condition picks, else null (all of them). */
function periodsKept(query: QueryRequest["query"], request: QueryRequest): number | null {
  if (
    request.filters.period !== null &&
    query.where.some(
      (condition) => isPlaceholderCondition(condition) && condition.placeholder === "period",
    )
  )
    return 1;
  const picked = query.where.filter(
    (condition): condition is { column: string; values: string[] } =>
      !isPlaceholderCondition(condition) &&
      condition.column === "period" &&
      condition.values.length > 0,
  );
  if (picked.length === 0) return null;
  // The conditions are ANDed, so only the periods every one of them names are kept.
  const kept = picked
    .map((condition) => new Set(condition.values))
    .reduce((common, values) => new Set([...common].filter((value) => values.has(value))));
  return Math.max(kept.size, 1);
}

/**
 * The aggregate a query of a timed rate or price really runs: summing power
 * or prices over time gives no meaningful unit, so a sum averages there (a
 * rate still adds up over places at each snapshot). Amounts and per-period
 * values sum as asked.
 */
export function effectiveAggregate(kind: ValueKind, aggregate: Aggregate): Aggregate {
  return aggregate === "sum" && (kind === "power" || kind === "price") ? "avg" : aggregate;
}

/** A grouped column as a label: a snapshot as its time (with the period when more than one is shown). */
function labelSql(name: string, withPeriod: boolean): string {
  if (name !== "snapshot") return `coalesce(CAST(${column(name)} AS VARCHAR), '(none)')`;
  const time = "strftime(snapshot.timestep, '%-d %b %H:%M')";
  return withPeriod ? `CAST(snapshot.period AS VARCHAR) || ' · ' || ${time}` : time;
}

/** The widget's query as SQL over its source query (which reads plain record names). */
function widgetSql(source: ResultQuery, request: QueryRequest): string {
  const { query } = request;
  // A sum over time of a rate or a price isn't a quantity: they average instead (see effectiveAggregate).
  const aggregate = effectiveAggregate(source.kind, query.aggregate);
  const where = conditions(request);
  const from = `${source.name}${where.length > 0 ? ` WHERE ${where.join(" AND ")}` : ""}`;
  const groups = query.groupBy;
  const keys = ["x", "s"].slice(0, groups.length);
  const timed = source.columns.includes("snapshot");
  // A sum over several periods is an average period's (a year's), not the periods added up.
  const periods = periodsKept(query, request);
  const perPeriod =
    aggregate === "sum" &&
    source.columns.includes("period") &&
    !groups.includes("period") &&
    // A snapshot belongs to one period, so its group is already a period's.
    !groups.includes("snapshot") &&
    periods !== 1
      ? periods === null
        ? " / (SELECT count(DISTINCT snapshot.period) FROM dims.snapshot)"
        : ` / ${periods}`
      : "";
  const order =
    groups[0] === "snapshot"
      ? "epoch(any_value(snapshot.timestep)) + 1e10 * any_value(snapshot.period)"
      : "NULL::DOUBLE";
  if (source.kind === "static" || !timed) {
    const selects = groups.map((name, index) => `${labelSql(name, true)} AS ${keys[index]}`);
    return `SELECT ${[...selects, `${AGGREGATES[aggregate]}(value)${perPeriod} AS value`, `${order} AS o`].join(", ")} FROM ${from}${groups.length ? " GROUP BY ALL" : ""}`;
  }
  // Per snapshot first (summing or averaging over places), then over snapshots.
  const { space, time } = timedAggregates(source.kind, aggregate);
  const hours = source.weighted ? "any_value(w)" : "1";
  const inner = `SELECT ${[...groups.filter((name) => name !== "snapshot").map(column), "snapshot", `${space}(value) AS v`, `${hours} AS w`].join(", ")} FROM ${from} GROUP BY ALL`;
  const selects = groups.map(
    (name, index) => `${labelSql(name, request.filters.period === null)} AS ${keys[index]}`,
  );
  return `SELECT ${[...selects, `${time}${perPeriod} AS value`, `${order} AS o`].join(", ")} FROM (${inner})${groups.length ? " GROUP BY ALL" : ""}`;
}

function roundValue(value: number) {
  return Math.abs(value) >= 100 ? Math.round(value * 10) / 10 : Number(value.toPrecision(3));
}

async function runQuery(request: QueryRequest): Promise<QueryResult> {
  const source = allQueries().find((query) => query.name === request.query.table);
  if (!source)
    throw new Error(`There's no query named "${request.query.table}". Pick another in the editor.`);
  const rows = await runResultSql<{
    x?: string;
    s?: string;
    value: number | null;
    o: number | null;
  }>(request.result, widgetSql(source, request));
  const { query } = request;
  const [xColumn = null, seriesColumn = null] = query.groupBy;

  // X labels in time order for snapshots, else by name; series by name.
  const firstOrder = new Map<string, number>();
  for (const row of rows)
    if (row.o !== null && !firstOrder.has(row.x ?? "")) firstOrder.set(row.x ?? "", Number(row.o));
  const byName = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });
  let xLabels = [...new Set(rows.map((row) => row.x ?? ""))].sort(
    xColumn === "snapshot" ? (a, b) => firstOrder.get(a)! - firstOrder.get(b)! : byName,
  );
  const seriesLabels = seriesColumn
    ? [...new Set(rows.map((row) => row.s ?? ""))].sort(byName)
    : [null];
  // Labels can hold any character, so cells are keyed by x then series, not by a joined string.
  const cells = new Map<string, Map<string, number | null>>();
  for (const row of rows) {
    const x = row.x ?? "";
    if (!cells.has(x)) cells.set(x, new Map());
    cells.get(x)!.set(row.s ?? "", row.value === null ? null : Number(row.value));
  }
  // Unrounded, so ordering and the limit don't tie values that only differ past the rounding.
  let matrix = xLabels.map((x) => seriesLabels.map((s) => cells.get(x)?.get(s ?? "") ?? null));

  // Ordering and the limit pick X-axis labels; with series, by their total.
  if (query.orderBy) {
    const sign = query.orderBy.direction === "asc" ? 1 : -1;
    const ordered = xLabels.map((label, index) => ({
      label,
      index,
      total: matrix[index].reduce<number>((sum, value) => sum + (value ?? 0), 0),
    }));
    ordered.sort(
      (a, b) =>
        sign * (query.orderBy!.by === "value" ? a.total - b.total : byName(a.label, b.label)),
    );
    xLabels = ordered.map((item) => item.label);
    matrix = ordered.map((item) => matrix[item.index]);
  }
  if (query.limit !== null) {
    xLabels = xLabels.slice(0, query.limit);
    matrix = matrix.slice(0, query.limit);
  }
  const series = seriesLabels
    .map((label, index) => ({
      name: label ?? source.valueLabel,
      values: matrix.map((row) => (row[index] === null ? null : roundValue(row[index]))),
    }))
    .filter((item) => item.values.some((value) => value !== null));
  return {
    table: queryTableInfo(source),
    xColumn,
    seriesColumn,
    xLabels: xColumn ? xLabels : [""],
    series,
  };
}

export const recordResultSource: ResultSource = { loadPeriods, runQuery };
