import {
  RESULT_TABLES,
  resultTable,
  rowBusPrice,
  type ResultTable,
  type ResultTableRow,
} from "../data/result-tables";
import { simulate } from "./dispatch-simulation";
import { resultFactor } from "./result-comparison";
import {
  SNAPSHOT_COUNT,
  busWeight,
  carrierAllowed,
  hourRangeShare,
  seasonalFactor,
  snapshotLabel,
  snapshotRange,
  carrierGroupOf,
  type FilterDimension,
  type InspectFilters,
} from "./inspect-filters";

// A custom widget's query: one aggregate of `value` from one result table,
// grouped by up to two columns (the X axis, then the series). The builder
// edits it field by field; the SQL editor reads and writes it as SQL.
//
// Dummy for now: the SQL is parsed here and answered from the dummy result
// tables, not sent to DuckDB. Only the subset the builder can express parses.

export type Aggregate = "sum" | "avg" | "max" | "min";
export type Placeholder = "buses" | "snapshots" | "carriers";

export type QueryCondition =
  | { column: string; placeholder: Placeholder }
  | { column: string; values: string[] };

export type QueryOrder = { by: "value" | "label"; direction: "asc" | "desc" };

export interface CustomQuery {
  table: string;
  aggregate: Aggregate;
  /** [X axis, series], either may be absent. */
  groupBy: string[];
  where: QueryCondition[];
  orderBy: QueryOrder | null;
  /** Keeps the first N X-axis labels after ordering. */
  limit: number | null;
}

export const AGGREGATE_LABELS: Record<Aggregate, string> = {
  sum: "Sum",
  avg: "Average",
  max: "Maximum",
  min: "Minimum",
};

/** Each placeholder fills in one page filter, and belongs to one column. */
export const PLACEHOLDER_COLUMNS: Record<Placeholder, string> = {
  buses: "bus",
  snapshots: "snapshot",
  carriers: "carrier",
};
export const PLACEHOLDER_DIMENSIONS: Record<Placeholder, FilterDimension> = {
  buses: "bus",
  snapshots: "snapshot",
  carriers: "carrier",
};
export const PLACEHOLDERS = Object.keys(PLACEHOLDER_COLUMNS) as Placeholder[];

export function isPlaceholderCondition(
  condition: QueryCondition,
): condition is { column: string; placeholder: Placeholder } {
  return "placeholder" in condition;
}

/** The placeholders that apply to a table, one per page filter it has a column for. */
export function tablePlaceholders(table: ResultTable): Placeholder[] {
  return PLACEHOLDERS.filter((placeholder) =>
    table.columns.includes(PLACEHOLDER_COLUMNS[placeholder]),
  );
}

/** A query that follows every page filter the table can take. */
export function defaultQuery(tableName = RESULT_TABLES[0].name): CustomQuery {
  const table = resultTable(tableName) ?? RESULT_TABLES[0];
  const xColumn =
    table.columns.find((column) => column !== "snapshot" && column !== "bus") ?? table.columns[0];
  return {
    table: table.name,
    aggregate: table.kind === "price" || table.kind === "power" ? "avg" : "sum",
    groupBy: [xColumn],
    where: tablePlaceholders(table).map((placeholder) => ({
      column: PLACEHOLDER_COLUMNS[placeholder],
      placeholder,
    })),
    orderBy: null,
    limit: null,
  };
}

export function queryFilteredBy(query: CustomQuery): FilterDimension[] {
  return query.where
    .filter(isPlaceholderCondition)
    .map((condition) => PLACEHOLDER_DIMENSIONS[condition.placeholder]);
}

// ---------------------------------------------------------------- SQL text

const sqlString = (value: string) => `'${value.replaceAll("'", "''")}'`;

export function querySql(query: CustomQuery): string {
  const aggregate = `${query.aggregate.toUpperCase()}(value) AS value`;
  const lines = [`SELECT ${[...query.groupBy, aggregate].join(", ")}`, `FROM ${query.table}`];
  query.where.forEach((condition, index) => {
    const clause = isPlaceholderCondition(condition)
      ? `${condition.column} IN {{${condition.placeholder}}}`
      : condition.values.length === 1
        ? `${condition.column} = ${sqlString(condition.values[0])}`
        : `${condition.column} IN (${condition.values.map(sqlString).join(", ")})`;
    lines.push(`${index === 0 ? "WHERE" : "  AND"} ${clause}`);
  });
  if (query.groupBy.length > 0) lines.push(`GROUP BY ${query.groupBy.join(", ")}`);
  if (query.orderBy)
    lines.push(
      `ORDER BY ${query.orderBy.by === "value" ? "value" : (query.groupBy[0] ?? "value")} ${query.orderBy.direction.toUpperCase()}`,
    );
  if (query.limit !== null) lines.push(`LIMIT ${query.limit}`);
  return lines.join("\n");
}

export type ParseResult = { ok: true; query: CustomQuery } | { ok: false; error: string };

const AGGREGATE_NAMES: Record<string, Aggregate> = {
  sum: "sum",
  avg: "avg",
  mean: "avg",
  max: "max",
  min: "min",
};

function splitTopLevel(text: string, separator: RegExp) {
  const parts: string[] = [];
  let depth = 0;
  let quoted = false;
  let current = "";
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (character === "'") quoted = !quoted;
    if (!quoted && character === "(") depth++;
    if (!quoted && character === ")") depth--;
    if (!quoted && depth === 0) {
      const match = text.slice(index).match(separator);
      if (match?.index === 0) {
        parts.push(current);
        current = "";
        index += match[0].length - 1;
        continue;
      }
    }
    current += character;
  }
  parts.push(current);
  return parts.map((part) => part.trim()).filter(Boolean);
}

function parseStrings(list: string): string[] | null {
  const values = splitTopLevel(list, /^,/).map((item) =>
    item.match(/^'((?:[^']|'')*)'$/)?.[1]?.replaceAll("''", "'"),
  );
  return values.every((value) => value !== undefined) ? (values as string[]) : null;
}

/** Reads the SQL the builder writes back into a query, or says what it can't read. */
export function parseQuerySql(sql: string): ParseResult {
  const text = sql
    .replaceAll(/--[^\n]*/g, "")
    .replaceAll(/\s+/g, " ")
    .trim()
    .replace(/;$/, "")
    .trim();
  const match = text.match(
    /^SELECT (.+?) FROM ([\w.]+)(?: WHERE (.+?))?(?: GROUP BY (.+?))?(?: ORDER BY (.+?))?(?: LIMIT (\d+))?$/i,
  );
  if (!match)
    return {
      ok: false,
      error: "Expected SELECT … FROM <table> [WHERE …] [GROUP BY …] [ORDER BY …] [LIMIT n].",
    };
  const [, selectList, tableName, whereText, groupText, orderText, limitText] = match;

  const table = resultTable(tableName.replace(/^results\./i, "").toLowerCase());
  if (!table)
    return {
      ok: false,
      error: `Unknown table "${tableName}". Tables: ${RESULT_TABLES.map((item) => item.name).join(", ")}.`,
    };
  const checkColumn = (column: string) =>
    table.columns.includes(column)
      ? null
      : `"${column}" is not a column of ${table.name}. Columns: ${table.columns.join(", ")}, value.`;

  let aggregate: Aggregate | null = null;
  let valueAlias = "value";
  const selected: string[] = [];
  for (const item of splitTopLevel(selectList, /^,/)) {
    const aggregateMatch = item.match(/^(\w+)\s*\(\s*value\s*\)(?:\s+AS\s+(\w+))?$/i);
    if (aggregateMatch) {
      const name = AGGREGATE_NAMES[aggregateMatch[1].toLowerCase()];
      if (!name)
        return {
          ok: false,
          error: `Unsupported aggregate ${aggregateMatch[1].toUpperCase()}. Use SUM, AVG, MAX or MIN.`,
        };
      if (aggregate) return { ok: false, error: "Select one aggregate of value." };
      aggregate = name;
      valueAlias = aggregateMatch[2] ?? "value";
      continue;
    }
    if (!/^\w+$/.test(item))
      return {
        ok: false,
        error: `Can't read "${item}". Select columns and one aggregate such as SUM(value).`,
      };
    const error = checkColumn(item.toLowerCase());
    if (error) return { ok: false, error };
    selected.push(item.toLowerCase());
  }
  if (!aggregate) return { ok: false, error: "Select an aggregate of value, such as SUM(value)." };
  if (selected.length > 2)
    return { ok: false, error: "Group by at most two columns: the X axis and the series." };

  const grouped = groupText
    ? splitTopLevel(groupText, /^,/).map((column) => column.toLowerCase())
    : [];
  if (grouped.length !== selected.length || grouped.some((column) => !selected.includes(column))) {
    return {
      ok: false,
      error: `GROUP BY must list the selected columns${selected.length ? `: ${selected.join(", ")}` : ""}.`,
    };
  }

  const where: QueryCondition[] = [];
  for (const clause of whereText ? splitTopLevel(whereText, /^ AND /i) : []) {
    const placeholderMatch = clause.match(/^(\w+) IN \{\{\s*(\w+)\s*\}\}$/i);
    const listMatch = clause.match(/^(\w+) IN \((.+)\)$/i);
    const equalsMatch = clause.match(/^(\w+) = ('(?:[^']|'')*')$/);
    const column = (placeholderMatch ?? listMatch ?? equalsMatch)?.[1]?.toLowerCase();
    if (!column)
      return {
        ok: false,
        error: `Can't read the condition "${clause}". Use column IN {{placeholder}}, column IN ('a', 'b') or column = 'a'.`,
      };
    const error = checkColumn(column);
    if (error) return { ok: false, error };
    if (placeholderMatch) {
      const placeholder = placeholderMatch[2].toLowerCase() as Placeholder;
      if (!PLACEHOLDERS.includes(placeholder))
        return {
          ok: false,
          error: `Unknown placeholder {{${placeholderMatch[2]}}}. Use ${PLACEHOLDERS.map((name) => `{{${name}}}`).join(", ")}.`,
        };
      if (PLACEHOLDER_COLUMNS[placeholder] !== column)
        return {
          ok: false,
          error: `{{${placeholder}}} filters the ${PLACEHOLDER_COLUMNS[placeholder]} column, not ${column}.`,
        };
      where.push({ column, placeholder });
      continue;
    }
    if (column === "snapshot")
      return {
        ok: false,
        error: "Filter snapshots with snapshot IN {{snapshots}}, which follows the page filter.",
      };
    const values = parseStrings(listMatch ? listMatch[2] : equalsMatch![2]);
    if (!values || values.length === 0)
      return { ok: false, error: `List quoted values in "${clause}".` };
    where.push({ column, values });
  }

  let orderBy: QueryOrder | null = null;
  if (orderText) {
    const orderMatch = orderText.match(/^(\w+)(?: (ASC|DESC))?$/i);
    const by = orderMatch?.[1]?.toLowerCase();
    if (!orderMatch || !by) return { ok: false, error: `Can't read ORDER BY ${orderText}.` };
    const direction = (orderMatch[2]?.toLowerCase() ?? "asc") as QueryOrder["direction"];
    if (by === valueAlias.toLowerCase() || by === "value") orderBy = { by: "value", direction };
    else if (by === selected[0]) orderBy = { by: "label", direction };
    else
      return {
        ok: false,
        error: `Order by ${valueAlias} or the X axis column${selected[0] ? ` (${selected[0]})` : ""}.`,
      };
  }

  return {
    ok: true,
    query: {
      table: table.name,
      aggregate,
      groupBy: selected,
      where,
      orderBy,
      limit: limitText ? Number(limitText) : null,
    },
  };
}

// ---------------------------------------------------------------- Results

export interface QueryResult {
  table: ResultTable;
  xColumn: string | null;
  seriesColumn: string | null;
  xLabels: string[];
  series: { name: string; values: (number | null)[] }[];
}

interface QueryContext {
  filters: InspectFilters;
  allBuses: string[];
  resultId: string;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface HourBucket {
  label: string;
  start: number;
  end: number;
}

// Snapshots on an axis: hourly up to three weeks, daily up to four months,
// then monthly, so a chart never carries thousands of points.
function hourBuckets(start: number, end: number): HourBucket[] {
  const length = end - start + 1;
  if (length <= 21 * 24)
    return Array.from({ length }, (_, index) => ({
      label: snapshotLabel(start + index),
      start: start + index,
      end: start + index,
    }));
  if (length <= 120 * 24) {
    const buckets: HourBucket[] = [];
    for (let hour = start - (start % 24); hour <= end; hour += 24)
      buckets.push({
        label: snapshotLabel(hour).slice(0, -6),
        start: Math.max(hour, start),
        end: Math.min(hour + 23, end),
      });
    return buckets;
  }
  return MONTHS.flatMap((month, index) => {
    const monthStart = Math.round((Date.UTC(2040, index, 1) - Date.UTC(2040, 0, 1)) / 3_600_000);
    const monthEnd =
      Math.round((Date.UTC(2040, index + 1, 1) - Date.UTC(2040, 0, 1)) / 3_600_000) - 1;
    const bucketStart = Math.max(monthStart, start);
    const bucketEnd = Math.min(monthEnd, end);
    return bucketStart <= bucketEnd ? [{ label: month, start: bucketStart, end: bucketEnd }] : [];
  });
}

// Each result differs from the first by a few percent per row, so a
// comparison has something to show; the first matches the built-in widgets.
function rowFactor(resultId: string, row: ResultTableRow) {
  return resultFactor(resultId, Object.values(row.labels).join("|"));
}

let yearDispatch: ReturnType<typeof simulate> | null = null;
function dispatchAt(carrier: string, hour: number) {
  yearDispatch ??= simulate(0, SNAPSHOT_COUNT - 1);
  return yearDispatch.carriers[carrier]?.[hour] ?? 0;
}

function sampledHours(start: number, end: number, maxSamples = 240) {
  const step = Math.max(1, Math.floor((end - start + 1) / maxSamples));
  const hours: number[] = [];
  for (let hour = start; hour <= end; hour += step) hours.push(hour);
  return hours;
}

interface Stats {
  sum: number;
  mean: number;
  max: number;
  min: number;
}

// One row's value over an hour range, at one bus or a share of the system.
function rowStats(
  table: ResultTable,
  row: ResultTableRow,
  start: number,
  end: number,
  bus: { name: string } | { share: number },
): Stats {
  const shapeLabel = table.shapeColumn ? row.labels[table.shapeColumn] : undefined;
  const group = shapeLabel ? carrierGroupOf(shapeLabel) : null;
  const hours = end - start + 1;
  const share = "share" in bus ? bus.share : 1;
  if (table.kind === "static") {
    const value = row.base * share;
    return { sum: value, mean: value, max: value, min: value };
  }
  if (table.kind === "energy") {
    const sum = row.base * share * hourRangeShare(start, end, shapeLabel);
    const samples = sampledHours(start, end).map(
      (hour) => (row.base * share * seasonalFactor(hour, group)) / SNAPSHOT_COUNT,
    );
    return { sum, mean: sum / hours, max: Math.max(...samples), min: Math.min(...samples) };
  }
  if (table.kind === "price") {
    const price = "name" in bus ? rowBusPrice(row, bus.name) : rowBusPrice(row, "system");
    const mean = price * (hourRangeShare(start, end, shapeLabel) / (hours / SNAPSHOT_COUNT));
    const samples = sampledHours(start, end).map((hour) => price * seasonalFactor(hour, group));
    return { sum: mean * hours, mean, max: Math.max(...samples), min: Math.min(...samples) };
  }
  const samples = sampledHours(start, end, 1000).map(
    (hour) => dispatchAt(row.labels.carrier, hour) * share,
  );
  const mean = samples.reduce((total, value) => total + value, 0) / samples.length;
  return { sum: mean * hours, mean, max: Math.max(...samples), min: Math.min(...samples) };
}

function combine(stats: Stats[], aggregate: Aggregate): number | null {
  if (stats.length === 0) return null;
  if (aggregate === "sum") return stats.reduce((total, item) => total + item.sum, 0);
  if (aggregate === "avg")
    return stats.reduce((total, item) => total + item.mean, 0) / stats.length;
  if (aggregate === "max") return Math.max(...stats.map((item) => item.max));
  return Math.min(...stats.map((item) => item.min));
}

function roundValue(value: number) {
  return Math.abs(value) >= 100 ? Math.round(value * 10) / 10 : Number(value.toPrecision(3));
}

export function runQuery(
  query: CustomQuery,
  { filters, allBuses, resultId }: QueryContext,
): QueryResult | { error: string } {
  const table = resultTable(query.table);
  if (!table) return { error: `Unknown table "${query.table}".` };

  // What the conditions leave of each dimension.
  let rows = table.rows;
  let buses = allBuses;
  let busFiltered = false;
  let [start, end] = [0, SNAPSHOT_COUNT - 1];
  for (const condition of query.where) {
    if (isPlaceholderCondition(condition)) {
      if (condition.placeholder === "buses" && filters.buses.length > 0) {
        buses = buses.filter((bus) => filters.buses.includes(bus));
        busFiltered = true;
      }
      if (condition.placeholder === "snapshots") [start, end] = snapshotRange(filters.snapshots);
      if (condition.placeholder === "carriers")
        rows = rows.filter((row) => carrierAllowed(filters, row.labels.carrier ?? ""));
    } else if (condition.column === "bus") {
      buses = buses.filter((bus) => condition.values.includes(bus));
      busFiltered = true;
    } else {
      rows = rows.filter((row) => condition.values.includes(row.labels[condition.column] ?? ""));
    }
  }

  const totalWeight = allBuses.reduce((sum, bus) => sum + busWeight(bus), 0) || 1;
  const busShareOf = (names: string[]) =>
    allBuses.length === 0 ? 1 : names.reduce((sum, bus) => sum + busWeight(bus), 0) / totalWeight;
  const [xColumn = null, seriesColumn = null] = query.groupBy;

  // Labels of a grouped column, in table order.
  const columnLabels = (column: string): string[] => {
    if (column === "bus") return [...buses].sort((a, b) => a.localeCompare(b));
    if (column === "snapshot") return hourBuckets(start, end).map((bucket) => bucket.label);
    return [
      ...new Set(
        rows
          .map((row) => row.labels[column])
          .filter((label): label is string => label !== undefined),
      ),
    ];
  };
  const buckets = new Map(hourBuckets(start, end).map((bucket) => [bucket.label, bucket]));

  // The value of one cell: every row, bus and hour its labels leave.
  const cell = (labels: Record<string, string>): number | null => {
    const cellRows = rows.filter((row) =>
      Object.entries(labels).every(
        ([column, label]) =>
          column === "bus" || column === "snapshot" || row.labels[column] === label,
      ),
    );
    const bucket = labels.snapshot ? buckets.get(labels.snapshot) : undefined;
    const [cellStart, cellEnd] = bucket ? [bucket.start, bucket.end] : [start, end];
    const cellBuses = labels.bus ? [labels.bus] : buses;
    if (cellRows.length === 0 || (busFiltered && cellBuses.length === 0)) return null;
    const stats = cellRows.flatMap((row) => {
      const factor = rowFactor(resultId, row);
      const scale = (item: Stats): Stats => ({
        sum: item.sum * factor,
        mean: item.mean * factor,
        max: item.max * factor,
        min: item.min * factor,
      });
      // Prices are per bus; everything else is a share of the system total.
      if (table.kind === "price")
        return (cellBuses.length > 0 ? cellBuses : ["system"]).map((bus) =>
          scale(rowStats(table, row, cellStart, cellEnd, { name: bus })),
        );
      return [
        scale(
          rowStats(table, row, cellStart, cellEnd, {
            share: labels.bus || busFiltered ? busShareOf(cellBuses) : 1,
          }),
        ),
      ];
    });
    const value = combine(stats, query.aggregate);
    return value === null ? null : roundValue(value);
  };

  let xLabels = xColumn ? columnLabels(xColumn) : [""];
  const seriesLabels = seriesColumn ? columnLabels(seriesColumn) : [null];
  const valueOf = (xLabel: string, seriesLabel: string | null) =>
    cell({
      ...(xColumn ? { [xColumn]: xLabel } : {}),
      ...(seriesColumn && seriesLabel !== null ? { [seriesColumn]: seriesLabel } : {}),
    });
  let matrix = xLabels.map((xLabel) =>
    seriesLabels.map((seriesLabel) => valueOf(xLabel, seriesLabel)),
  );

  // Ordering and the limit pick X-axis labels; with series, by their total.
  if (query.orderBy) {
    const sign = query.orderBy.direction === "asc" ? 1 : -1;
    const order = xLabels.map((label, index) => ({
      label,
      index,
      total: matrix[index].reduce<number>((sum, value) => sum + (value ?? 0), 0),
    }));
    order.sort(
      (a, b) =>
        sign *
        (query.orderBy!.by === "value"
          ? a.total - b.total
          : a.label.localeCompare(b.label, undefined, { numeric: true })),
    );
    xLabels = order.map((item) => item.label);
    matrix = order.map((item) => matrix[item.index]);
  }
  if (query.limit !== null) {
    xLabels = xLabels.slice(0, query.limit);
    matrix = matrix.slice(0, query.limit);
  }

  // Series with nothing in them (a carrier the conditions dropped) are left out.
  const series = seriesLabels
    .map((label, seriesIndex) => ({
      name: label ?? table.valueLabel,
      values: matrix.map((row) => row[seriesIndex]),
    }))
    .filter((item) => item.values.some((value) => value !== null));
  return { table, xColumn, seriesColumn, xLabels, series };
}
