import * as duckdb from "@duckdb/duckdb-wasm";
import { isSecure, recordServerConfig } from "../../../home/lib/record-server";
import type { RecordServerConfig } from "../../../home/lib/record-server";

// The one place that knows how the browser reaches the record server:
// DuckDB-Wasm in a worker, the Quack extension, and an ATTACH of the server's
// record as `r`. Everything else asks for rows through query()/serverQuery().
//
// DuckDB 2.0 has no stable DuckDB-Wasm release yet, so this runs the
// 1.33.1-dev110.0 build (exactly DuckDB v2.0.0) with the extensions the server
// relabels and serves from /ext (server/README.md). They're unsigned, hence
// allowUnsignedExtensions. When DuckDB-Wasm and Quack publish their v2.0.0
// builds, only this file changes.

// The server address and token come from features/home/lib/record-server.ts,
// which the project catalogue reads too.

export function serverUrl(path: string, config = recordServerConfig()): string {
  return `${isSecure(config.server) ? "https" : "http"}://${config.server}${path}`;
}

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

let status: ConnectionStatus = "connecting";
const statusListeners = new Set<(status: ConnectionStatus) => void>();

function setStatus(next: ConnectionStatus) {
  if (next === status) return;
  status = next;
  for (const listener of statusListeners) listener(next);
}

export function connectionStatus(): ConnectionStatus {
  return status;
}

export function onConnectionStatus(listener: (status: ConnectionStatus) => void): () => void {
  statusListeners.add(listener);
  return () => statusListeners.delete(listener);
}

// The server drops a link it hasn't heard from within its heartbeat timeout.
// Quack's own heartbeats need a background thread, which single-threaded
// DuckDB-Wasm can't start, so here every query renews the lease instead: the
// link checks below while the tab is visible. The long timeout lets a hidden
// tab, whose checks pause, keep its link; the server's default is 60 s.
const HEARTBEAT_TIMEOUT_S = 3_600;

async function attach(connection: duckdb.AsyncDuckDBConnection, config: RecordServerConfig) {
  const [host, port] = config.server.split(":");
  const secure = isSecure(config.server);
  await connection.query(
    `ATTACH 'quack:${host}:${port ?? (secure ? 443 : 80)}' AS r ` +
      `(TOKEN '${config.token.replaceAll("'", "''")}', DISABLE_SSL ${!secure}, HEARTBEAT_TIMEOUT ${HEARTBEAT_TIMEOUT_S})`,
  );
}

async function connect(config: RecordServerConfig): Promise<duckdb.AsyncDuckDBConnection> {
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  // A cross-origin worker script can't be started directly; a blob can import it.
  const bootstrap = URL.createObjectURL(
    new Blob([`importScripts(${JSON.stringify(bundle.mainWorker)});`], { type: "text/javascript" }),
  );
  const worker = new Worker(bootstrap);
  URL.revokeObjectURL(bootstrap);

  const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  await db.open({ allowUnsignedExtensions: true });
  const connection = await db.connect();

  await connection.query(`SET custom_extension_repository = '${serverUrl("/ext", config)}'`);
  await connection.query("LOAD quack");
  await attach(connection, config);
  return connection;
}

let connecting: Promise<duckdb.AsyncDuckDBConnection> | null = null;

// One connection per page load, shared by every caller. A failed attempt is
// forgotten so the next call can retry.
export function connectRecord(): Promise<duckdb.AsyncDuckDBConnection> {
  if (!connecting) {
    setStatus("connecting");
    connecting = connect(recordServerConfig()).then(
      (connection) => {
        setStatus("connected");
        startChecks();
        return connection;
      },
      (error: unknown) => {
        connecting = null;
        setStatus("disconnected");
        throw error;
      },
    );
  }
  return connecting;
}

// Restores the link to the server: the browser's DuckDB keeps running and
// only `r` is attached again. Before a first successful connect, it connects.
export async function reconnectRecord(): Promise<void> {
  const current = connecting;
  if (!current) {
    await connectRecord();
    return;
  }
  setStatus("connecting");
  try {
    const connection = await current;
    await connection.query("DETACH DATABASE IF EXISTS r");
    await attach(connection, recordServerConfig());
    setStatus("connected");
  } catch (error) {
    setStatus("disconnected");
    throw error;
  }
}

// Checks the link every few seconds with a query the server answers, so a
// broken link shows before someone clicks into it. Quack has no ping that SQL
// can reach: quack_connection_id() answers locally, without the server. Paused while the tab is
// hidden, so an idle tab doesn't keep a Cloud Run instance awake.
const CHECK_INTERVAL_MS = 15_000;
// Generous enough for a Cloud Run cold start after idling.
const CHECK_TIMEOUT_MS = 15_000;
let pending = 0;
let checking = false;
let checksStarted = false;

async function checkLink() {
  if (checking || pending > 0 || status === "connecting" || !connecting) return;
  checking = true;
  try {
    const connection = await connecting;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error("timed out")), CHECK_TIMEOUT_MS);
    });
    try {
      await Promise.race([connection.query("FROM quack_query_by_name('r', 'SELECT 1')"), timeout]);
    } finally {
      clearTimeout(timer);
    }
    if (connectionStatus() !== "connecting") setStatus("connected");
  } catch {
    if (connectionStatus() !== "connecting") setStatus("disconnected");
  } finally {
    checking = false;
  }
}

function startChecks() {
  if (checksStarted) return;
  checksStarted = true;
  setInterval(() => {
    if (document.visibilityState === "visible") void checkLink();
  }, CHECK_INTERVAL_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void checkLink();
  });
}

// Arrow values as plain JSON-ish values: BIGINT counts become numbers, lists
// and structs become arrays and objects.
function toPlain(value: unknown): unknown {
  if (typeof value === "bigint") return Number(value);
  if (
    value === null ||
    typeof value !== "object" ||
    value instanceof Date ||
    ArrayBuffer.isView(value)
  )
    return value;
  if (Array.isArray(value)) return value.map(toPlain);
  if (typeof (value as { toJSON?: unknown }).toJSON === "function")
    return toPlain((value as { toJSON: () => unknown }).toJSON());
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, toPlain(item)]));
}

// Runs in the browser's DuckDB; `r.<schema>.<view>` reads the server's record.
// A failed query may be a SQL error rather than a broken link, so it doesn't
// set the status itself; it checks the link right away instead.
export async function query<T>(sql: string): Promise<T[]> {
  const connection = await connectRecord();
  pending += 1;
  let table;
  try {
    table = await connection.query(sql);
  } catch (error) {
    pending -= 1;
    void checkLink();
    throw error;
  }
  pending -= 1;
  return table.toArray().map((row) => toPlain(row.toJSON()) as T);
}

// Runs entirely on the server, next to the data: for joins and aggregations
// over the attribute views, where only the result should travel.
export function serverQuery<T>(sql: string): Promise<T[]> {
  if (sql.includes("$$")) throw new Error("serverQuery: the SQL may not contain $$");
  return query<T>(`FROM quack_query_by_name('r', $$${sql}$$)`);
}

export async function fetchApi<T>(path: string, method: "GET" | "POST" = "GET"): Promise<T> {
  const config = recordServerConfig();
  const response = await fetch(serverUrl(path, config), {
    method,
    headers: { Authorization: `Bearer ${config.token}` },
  });
  if (!response.ok) {
    if (response.status === 401) throw new Error("The record server refused the token.");
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${method} ${path}: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

// The catalog of the record and scenario the app reads
// (`<record>__<scenario>`); null before a record has loaded.
let catalog: string | null = null;

export function recordCatalog(): string | null {
  return catalog;
}

export function setRecordCatalog(next: string | null): void {
  catalog = next;
}

// A record view, `schema.view`, in the active catalog, as serverQuery reads it.
export function serverName(name: string): string {
  return catalog ? `${catalog}.${name}` : name;
}

// A SQL string literal.
export function sqlString(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

// A SQL identifier, for view names with spaces ("energy to power ratio").
export function sqlName(name: string): string {
  return `"${name.replaceAll('"', '""')}"`;
}
