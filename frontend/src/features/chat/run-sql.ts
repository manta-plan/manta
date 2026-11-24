import { recordCatalog, serverQuery } from "../project/lib/record-server/client";

// The model's SQL is untrusted text. It runs only through serverQuery, on the
// record server, whose own guard allows nothing but reads. It never runs
// in the browser's DuckDB (query()), which can attach databases and read
// URLs. Everything about running such a query is in this file: the record
// server is temporary, and its replacement changes only what is here.

export const ROW_LIMIT = 200;
const TIMEOUT_MS = 20_000;

export interface SqlReply {
  /** The reply's text before and after the query. */
  before: string;
  sql: string;
  after: string;
}

export interface SqlResult {
  columns: string[];
  rows: Record<string, unknown>[];
  /** Whether the query had more than ROW_LIMIT rows. */
  truncated: boolean;
}

const FENCED = /```(?:sql)?[ \t]*\n([\s\S]*?)```/i;
const QUERY_START = /^(select|with|from)\b/i;
// `attributes.p_nom`, but not `x.attributes.p_nom` or `"attributes".p_nom`.
const SCHEMA_NAME = /(?<![\w."])(attributes|properties|dims|manta)\./;

/**
 * The query in a reply and the text around it, or null for a reply without
 * one. A small model sometimes leaves the fence out, so a reply that starts
 * with a query counts too: the query then ends at the first empty line.
 */
export function splitSqlReply(text: string): SqlReply | null {
  const fenced = FENCED.exec(text);
  if (fenced && QUERY_START.test(fenced[1].trim())) {
    return {
      before: text.slice(0, fenced.index).trim(),
      sql: fenced[1].trim(),
      after: text.slice(fenced.index + fenced[0].length).trim(),
    };
  }

  const trimmed = text.trim();
  if (fenced || !QUERY_START.test(trimmed)) return null;
  const end = trimmed.search(/\n\s*\n/);
  const sql = end === -1 ? trimmed : trimmed.slice(0, end).trim();
  // "Select New run on the Run tab." starts like a query too. A query names a view.
  if (!SCHEMA_NAME.test(sql)) return null;
  return { before: "", sql, after: end === -1 ? "" : trimmed.slice(end).trim() };
}

/**
 * The statement to run for a model's query: the one query, reading the given
 * catalog, cut off after ROW_LIMIT rows. Throws for anything that is not a
 * single SELECT. Wrapping it as a subquery makes the server's parser enforce
 * the same.
 */
export function prepareSql(sql: string, catalog: string): string {
  const statement = sql.trim().replace(/;\s*$/, "");
  if (statement.includes(";")) throw new Error("The query has more than one statement.");
  // serverQuery quotes the query with $$.
  if (statement.includes("$$")) throw new Error("The query may not contain $$.");
  if (!QUERY_START.test(statement)) throw new Error("Only a SELECT query can run.");
  if (!/^\w+$/.test(catalog)) throw new Error("No data record is open.");

  // The line breaks keep a trailing `--` comment from swallowing the bracket.
  const qualified = statement.replace(new RegExp(SCHEMA_NAME, "g"), `${catalog}.$1.`);
  return `SELECT * FROM (\n${qualified}\n) LIMIT ${ROW_LIMIT + 1}`;
}

/**
 * Runs a model's query on the open record and scenario. A query that runs
 * longer than the timeout is given up on, but not cancelled: the page's one
 * connection to the record server has no cancel, so the app's own reads wait
 * behind it.
 */
export async function runSql(sql: string): Promise<SqlResult> {
  const statement = prepareSql(sql, recordCatalog() ?? "");
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error("The query took too long.")), TIMEOUT_MS);
  });
  try {
    const rows = await Promise.race([serverQuery<Record<string, unknown>>(statement), timeout]);
    return {
      columns: rows.length > 0 ? Object.keys(rows[0]) : [],
      rows: rows.slice(0, ROW_LIMIT),
      truncated: rows.length > ROW_LIMIT,
    };
  } finally {
    clearTimeout(timer);
  }
}

const ERROR_CHARS = 500;

/** A failed query's error, short enough to show and to send back to the model. */
export function sqlErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message.trim().slice(0, ERROR_CHARS);
}
