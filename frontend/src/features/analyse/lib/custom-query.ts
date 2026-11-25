import type { FilterDimension } from "./inspect-filters";
import type { ResultTableInfo } from "./result-source";

// A custom widget's query: one aggregate of `value` from one result table,
// grouped by up to two columns (the X axis, then the series). The builder
// edits it field by field; the SQL editor reads and writes it as SQL.
//
// The SQL editor only accepts the subset the builder can express, parsed
// here. The query is answered by the result source (see resultSource.ts),
// which compiles it to SQL over the record's results.

export type Aggregate = "sum" | "avg" | "max" | "min";
export type Placeholder = "period" | "buses" | "carriers";

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
  period: "period",
  buses: "bus",
  carriers: "carrier",
};
export const PLACEHOLDER_DIMENSIONS: Record<Placeholder, FilterDimension> = {
  period: "period",
  buses: "bus",
  carriers: "carrier",
};
export const PLACEHOLDERS = Object.keys(PLACEHOLDER_COLUMNS) as Placeholder[];

export function isPlaceholderCondition(
  condition: QueryCondition,
): condition is { column: string; placeholder: Placeholder } {
  return "placeholder" in condition;
}

/** The placeholders that apply to a table, one per page filter it has a column for. */
export function tablePlaceholders(table: ResultTableInfo): Placeholder[] {
  return PLACEHOLDERS.filter((placeholder) =>
    table.columns.includes(PLACEHOLDER_COLUMNS[placeholder]),
  );
}

/** What a new custom widget starts with: supply by carrier, following every page filter. */
export const DEFAULT_QUERY: CustomQuery = {
  table: "supply",
  aggregate: "sum",
  groupBy: ["carrier"],
  where: PLACEHOLDERS.map((placeholder) => ({
    column: PLACEHOLDER_COLUMNS[placeholder],
    placeholder,
  })),
  orderBy: null,
  limit: null,
};

/** A query of one table that follows every page filter it can take. */
export function defaultQuery(table: ResultTableInfo): CustomQuery {
  const xColumn =
    table.columns.find(
      (column) => column !== "snapshot" && column !== "bus" && column !== "period",
    ) ?? table.columns[0];
  return {
    table: table.name,
    aggregate: table.defaultAggregate,
    groupBy: [xColumn],
    where: [
      ...tablePlaceholders(table).map((placeholder) => ({
        column: PLACEHOLDER_COLUMNS[placeholder],
        placeholder,
      })),
      // Prices of different bus carriers (AC, H2) don't average together: start on AC.
      ...(table.kind === "price" && table.columns.includes("carrier")
        ? [{ column: "carrier", values: ["AC"] }]
        : []),
    ],
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
  // A condition with nothing picked yet keeps everything, so it isn't written.
  query.where
    .filter((condition) => isPlaceholderCondition(condition) || condition.values.length > 0)
    .forEach((condition, index) => {
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
export function parseQuerySql(sql: string, tables: ResultTableInfo[]): ParseResult {
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

  const name = tableName.replace(/^results\./i, "").toLowerCase();
  const table = tables.find((item) => item.name === name);
  if (!table)
    return {
      ok: false,
      error: `Unknown table "${tableName}". Tables: ${tables.map((item) => item.name).join(", ")}.`,
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
        error:
          "Snapshots can't be filtered by value; pick a period with period IN {{period}}, which follows the page filter.",
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
  table: ResultTableInfo;
  xColumn: string | null;
  seriesColumn: string | null;
  xLabels: string[];
  series: { name: string; values: (number | null)[] }[];
}
