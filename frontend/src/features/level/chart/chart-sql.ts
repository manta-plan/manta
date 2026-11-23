import {
  serverName,
  serverQuery,
  sqlName,
  sqlString,
} from "../../project/lib/record-server/client";
import { levelCtes, spanCondition, type LevelQueryScope } from "../level-sql";
import { OUTPUT } from "../table/table-queries";

// The chart drawer's reads. Every time series comes back as one list per
// key (a carrier, an entity, a quantile), aligned to the window's snapshots
// in order, so a chart needs no joining in the browser: `loadAxis` gives the
// snapshots' times and the hours each stands for (snapshot_weighting_generators).
//
// Constants count at every snapshot of the window (a row without a snapshot
// holds for all of them), as baby-manta's demand() does.

const N = serverName;

export interface Axis {
  /** Epoch ms per snapshot of the window, in order. */
  times: number[];
  /** Hours each snapshot stands for. */
  weights: number[];
}

const toNumbers = (values: unknown): (number | null)[] =>
  Array.from((values ?? []) as ArrayLike<unknown>, (value) =>
    value === null || value === undefined ? null : Number(value),
  );

export async function loadAxis(scope: LevelQueryScope): Promise<Axis> {
  const rows = await serverQuery<{ t: number; w: number }>(`
    WITH span AS (SELECT snapshot FROM ${N("dims.snapshot")} WHERE ${spanCondition("snapshot", scope.period, scope.timeWindow)})
    SELECT epoch_ms(t.snapshot.timestep)::DOUBLE AS t, coalesce(w.value, 1)::DOUBLE AS w
    FROM span t LEFT JOIN ${N("attributes.snapshot_weighting_generators")} w ON w.snapshot = t.snapshot
    ORDER BY t.snapshot`);
  return { times: rows.map((row) => Number(row.t)), weights: rows.map((row) => Number(row.w)) };
}

/**
 * Runs `source` (rows of key, snapshot, v; one per key and snapshot) after
 * the level's CTEs and `ctes`, and returns each key's values over the
 * window, in snapshot order: missing snapshots are null (or 0 with `zero`).
 */
async function loadLists(
  scope: LevelQueryScope,
  ctes: string[],
  source: string,
  zero = false,
): Promise<Map<string, (number | null)[]>> {
  const rows = await serverQuery<{ key: string | null; vals: unknown }>(`
    WITH ${[levelCtes(scope), ...ctes, `src AS (${source})`, "keys AS (SELECT DISTINCT key FROM src)"].join(",\n")}
    SELECT k.key, list(${zero ? "coalesce(s.v, 0)" : "s.v"} ORDER BY t.snapshot) AS vals
    FROM span t CROSS JOIN keys k
    LEFT JOIN src s ON s.key IS NOT DISTINCT FROM k.key AND s.snapshot = t.snapshot
    GROUP BY k.key`);
  return new Map(rows.map((row) => [row.key ?? "", toNumbers(row.vals)]));
}

async function loadRows<T>(scope: LevelQueryScope, body: string): Promise<T[]> {
  return serverQuery<T>(`WITH ${levelCtes(scope)}${body}`);
}

// ------------------------------------------------------------ Attribute values

/** Where an attribute's values sit: per entity, per connection (entity and bus) or per bus. */
export type AttributeDim = "entity" | "connection" | "bus";

export function attributeDim(dims: readonly string[] | undefined): AttributeDim {
  if (dims?.includes("connection")) return "connection";
  if (dims?.includes("bus") && !dims.includes("entity")) return "bus";
  return "entity";
}

/**
 * A connection attribute's end: power (p) at the entity's own bus or a
 * branch's input (p0); anything else (efficiency) at its own bus or the
 * branch's output.
 */
function connectionRoles(attribute: string): string {
  return attribute === "p" ? "('attached', 'input')" : "('attached', 'output')";
}

/**
 * Rows of (key, snapshot, value) for an attribute over the window, for the
 * subjects `subjects` names (a query with columns key, subject, and bus for
 * a connection attribute at a given bus, else NULL). A constant counts at
 * every snapshot.
 */
function attributeValuesSql(
  scope: LevelQueryScope,
  attribute: string,
  dim: AttributeDim,
  subjects: string,
): string {
  const view = N(`attributes.${sqlName(attribute)}`);
  const span = spanCondition("a.snapshot", scope.period, scope.timeWindow);
  let from: string;
  if (dim === "entity") from = `${view} a JOIN (${subjects}) x ON x.subject = a.entity`;
  else if (dim === "bus") from = `${view} a JOIN (${subjects}) x ON x.subject = a.bus`;
  else
    from = `${view} a JOIN (${subjects}) x ON x.subject = a.connection.entity AND (x.bus = a.connection.bus OR (x.bus IS NULL AND a.connection IN (
      SELECT connection FROM ${N("properties.connection")} WHERE role IN ${connectionRoles(attribute)})))`;
  return `
    SELECT x.key, a.snapshot, a.value FROM ${from} WHERE ${span}
    UNION ALL
    SELECT x.key, t.snapshot, a.value FROM ${from} CROSS JOIN span t WHERE a.snapshot IS NULL`;
}

/** The level's buses: every real one, those at the location (or the selected ones), or the bus itself. */
function levelBusesSql(scope: LevelQueryScope, acOnly: boolean): string {
  const conditions = ["NOT b.virtual"];
  if (acOnly) conditions.push("b.carrier = 'AC'");
  if (scope.level.kind === "location")
    conditions.push(`b.location = ${sqlString(scope.level.location)}`);
  if (scope.level.kind === "bus") return `SELECT ${sqlString(scope.level.bus)} AS bus`;
  if (scope.locations && scope.locations.length > 0)
    conditions.push(`b.location IN (${scope.locations.map(sqlString).join(", ")})`);
  return `SELECT b.bus FROM ${N("manta.bus_location")} b WHERE ${conditions.join(" AND ")}`;
}

// ------------------------------------------------------------ Attributes mode

export interface AttributeOptionRow {
  ctype: string;
  attribute: string;
  /** Subjects storing it (constant or series). */
  n: number;
}

/** The series attributes of the level's members (and of its buses at a location level), and the types present. */
export async function loadAttributeOptions(
  scope: LevelQueryScope,
  withBuses: boolean,
): Promise<{ options: AttributeOptionRow[]; ctypes: string[] }> {
  const summary = N("manta.attribute_summary");
  const [entityRows, busRows, ctypes] = await Promise.all([
    loadRows<AttributeOptionRow>(
      scope,
      `
      SELECT m.ctype, s.attribute, count(DISTINCT m.entity)::INTEGER AS n
      FROM members m JOIN ${summary} s ON s.dim = 'entity' AND s.label = m.entity
      GROUP BY ALL
      HAVING bool_or(s.series_rows > 0)
      ORDER BY 1, 2`,
    ),
    withBuses
      ? loadRows<AttributeOptionRow>(
          scope,
          `
          SELECT 'Bus' AS ctype, s.attribute, count(DISTINCT s.label)::INTEGER AS n
          FROM ${summary} s WHERE s.dim = 'bus' AND s.label IN (${levelBusesSql(scope, false)})
          GROUP BY ALL
          HAVING bool_or(s.series_rows > 0)
          ORDER BY 2`,
        )
      : Promise.resolve([]),
    loadRows<{ ctype: string }>(scope, ` SELECT DISTINCT ctype FROM members ORDER BY 1`),
  ]);
  return {
    options: [...entityRows, ...busRows].map((row) => ({ ...row, n: Number(row.n) })),
    ctypes: ctypes.map((row) => row.ctype),
  };
}

export interface AttributeQuery {
  ctype: string;
  attribute: string;
  dim: AttributeDim;
  /** Weight for a capacity-weighted mean and the ranking of Each: optimised capacity in Inspect. */
  optimised: boolean;
}

/** The subjects of an attribute at the level, each with a weight: capacity, or for loads and buses null (ranked by size instead). */
function subjectsSql(scope: LevelQueryScope, query: AttributeQuery): string {
  if (query.ctype === "Bus")
    return `SELECT bus AS key, bus AS subject, NULL::VARCHAR AS bus, NULL::DOUBLE AS weight FROM (${levelBusesSql(scope, false)})`;
  const weight = query.optimised ? "coalesce(capacity_opt, capacity)" : "capacity";
  return `SELECT entity AS key, entity AS subject, NULL::VARCHAR AS bus, ${weight} AS weight FROM members WHERE ctype = ${sqlString(query.ctype)}`;
}

/** Sum, plain mean or capacity-weighted mean of the attribute over the level, per snapshot. */
export function loadAttributeAggregate(
  scope: LevelQueryScope,
  query: AttributeQuery,
  how: "sum" | "mean" | "weighted",
): Promise<Map<string, (number | null)[]>> {
  const value =
    how === "sum"
      ? "sum(v.value)"
      : how === "mean"
        ? "avg(v.value)"
        : "coalesce(sum(v.value * w.weight) / nullif(sum(w.weight), 0), avg(v.value))";
  return loadLists(
    scope,
    [
      `subj AS (${subjectsSql(scope, query)})`,
      `vals AS (${attributeValuesSql(scope, query.attribute, query.dim, "SELECT * FROM subj")})`,
    ],
    `SELECT 'value' AS key, v.snapshot, ${value} AS v FROM vals v JOIN subj w ON w.key = v.key GROUP BY v.snapshot`,
  );
}

/** The largest `limit` subjects' series, largest first: by capacity, else by their largest absolute value in the window. */
export async function loadAttributeEach(
  scope: LevelQueryScope,
  query: AttributeQuery,
  limit: number,
): Promise<{ key: string; values: (number | null)[] }[]> {
  const ctes = [
    `subj AS (${subjectsSql(scope, query)})`,
    `vals AS (${attributeValuesSql(scope, query.attribute, query.dim, "SELECT * FROM subj")})`,
  ];
  const ranked = await serverQuery<{ key: string }>(`
    WITH ${[levelCtes(scope), ...ctes].join(",\n")}
    SELECT v.key FROM vals v JOIN subj w ON w.key = v.key GROUP BY v.key
    ORDER BY coalesce(any_value(w.weight), max(abs(v.value))) DESC NULLS LAST, v.key LIMIT ${limit}`);
  if (ranked.length === 0) return [];
  const keys = ranked.map((row) => row.key);
  const lists = await loadLists(
    scope,
    ctes,
    `SELECT key, snapshot, max(value) AS v FROM vals WHERE key IN (${keys.map(sqlString).join(", ")}) GROUP BY ALL`,
  );
  return keys.filter((key) => lists.has(key)).map((key) => ({ key, values: lists.get(key)! }));
}

/** Min, P25, median, P75 and max of the attribute over the level at each snapshot. */
export async function loadAttributeDistribution(
  scope: LevelQueryScope,
  query: AttributeQuery,
): Promise<Map<string, (number | null)[]>> {
  const quantiles: [string, number][] = [
    ["min", 0],
    ["p25", 0.25],
    ["median", 0.5],
    ["p75", 0.75],
    ["max", 1],
  ];
  return loadLists(
    scope,
    [
      `subj AS (${subjectsSql(scope, query)})`,
      `vals AS (${attributeValuesSql(scope, query.attribute, query.dim, "SELECT * FROM subj")})`,
      `q AS (SELECT snapshot, quantile_cont(value, [${quantiles.map(([, q]) => q).join(", ")}]) AS q FROM vals GROUP BY snapshot)`,
    ],
    quantiles
      .map(
        ([name], index) =>
          `SELECT ${sqlString(name)} AS key, snapshot, q[${index + 1}] AS v FROM q`,
      )
      .join(" UNION ALL "),
  );
}

// ------------------------------------------------------------ Picked series

export interface PickQuery {
  attribute: string;
  dim: AttributeDim;
  /** The entity, or the bus for a bus attribute. */
  subject: string;
  /** A connection attribute's bus; null takes the entity's own end. */
  bus: string | null;
}

/** Each picked series over the window, in pick order. */
export async function loadPicked(
  scope: LevelQueryScope,
  picks: PickQuery[],
): Promise<(number | null)[][]> {
  const groups = new Map<string, { attribute: string; dim: AttributeDim; rows: string[] }>();
  picks.forEach((pick, index) => {
    const id = `${pick.attribute}\n${pick.dim}`;
    const group = groups.get(id) ?? { attribute: pick.attribute, dim: pick.dim, rows: [] };
    group.rows.push(
      `(${sqlString(String(index))}, ${sqlString(pick.subject)}, ${pick.bus === null ? "NULL::VARCHAR" : sqlString(pick.bus)})`,
    );
    groups.set(id, group);
  });
  const sources = [...groups.values()].map(
    (group) =>
      `SELECT key, snapshot, max(value) AS v FROM (${attributeValuesSql(scope, group.attribute, group.dim, `SELECT * FROM (VALUES ${group.rows.join(", ")}) p(key, subject, bus)`)}) GROUP BY ALL`,
  );
  if (sources.length === 0) return [];
  const lists = await loadLists(scope, [], sources.join(" UNION ALL "));
  const empty = (await loadAxis(scope)).times.map(() => null);
  return picks.map((_, index) => lists.get(String(index)) ?? empty);
}

// ------------------------------------------------------------ Statistics: time series

/** p_set summed over the level's loads (MW per snapshot). */
export async function loadTotalLoad(scope: LevelQueryScope): Promise<(number | null)[] | null> {
  const lists = await loadLists(
    scope,
    [
      `vals AS (${attributeValuesSql(scope, "p_set", "entity", "SELECT entity AS key, entity AS subject FROM members WHERE ctype = 'Load'")})`,
    ],
    `SELECT 'load' AS key, snapshot, sum(value) AS v FROM vals GROUP BY snapshot`,
  );
  return lists.get("load") ?? null;
}

/** Generators with a p_max_pu series: wind and solar (and run of river), whose output the weather sets. */
// Built per query: serverName needs the catalog shown then, not at import.
const vre = () =>
  `entity IN (SELECT label FROM ${N("manta.attribute_summary")} WHERE dim = 'entity' AND attribute = 'p_max_pu' AND series_rows > 0)`;

/**
 * Available generation (MW per snapshot): capacity × p_max_pu (1 where none
 * is stored), per carrier or in all. Optimised capacity in Inspect.
 */
export function loadAvailable(
  scope: LevelQueryScope,
  options: { optimised: boolean; vreOnly: boolean; byCarrier: boolean },
): Promise<Map<string, (number | null)[]>> {
  const cap = options.optimised ? "coalesce(capacity_opt, capacity)" : "capacity";
  return loadLists(
    scope,
    [
      `g AS (SELECT entity, carrier, ${cap} AS cap FROM members WHERE ctype = 'Generator'${options.vreOnly ? ` AND ${vre()}` : ""})`,
      `pu AS (${attributeValuesSql(scope, "p_max_pu", "entity", "SELECT entity AS key, entity AS subject FROM g")})`,
    ],
    `SELECT ${options.byCarrier ? "g.carrier" : "'all'"} AS key, t.snapshot, sum(g.cap * coalesce(pu.value, 1)) AS v
     FROM span t CROSS JOIN g LEFT JOIN pu ON pu.key = g.entity AND pu.snapshot = t.snapshot
     GROUP BY ALL`,
    true,
  );
}

/** Rows of (entity, carrier, ctype, bus, snapshot, p) for the level's members of `ctypes` in the window (a run result's p). */
function powerSql(scope: LevelQueryScope, ctypes: string[], extra = ""): string {
  const roles = ctypes
    .map(
      (ctype) =>
        `(m.ctype = ${sqlString(ctype)} AND c.role = ${sqlString(OUTPUT[ctype]?.role ?? "attached")})`,
    )
    .join(" OR ");
  // The table's rule for what counts as output (a storage unit's discharge, a line's flow in absolute value...), so both agree.
  const value = `CASE ${ctypes
    .map((ctype) => `WHEN m.ctype = ${sqlString(ctype)} THEN ${OUTPUT[ctype]?.value ?? "p.value"}`)
    .join(" ")} END`;
  return `
    SELECT m.entity, m.carrier, m.ctype, m.bus, p.snapshot, ${value} AS p
    FROM ${N("attributes.p")} p
    JOIN ${N("properties.connection")} c ON c.connection = p.connection
    JOIN members m ON m.entity = p.connection.entity
    WHERE (${roles}) AND ${spanCondition("p.snapshot", scope.period, scope.timeWindow)}${extra}`;
}

/** Power per snapshot (MW), per carrier or in all: a run result's p of the level's `ctypes`. */
export function loadPower(
  scope: LevelQueryScope,
  ctypes: string[],
  options: { byCarrier: boolean; vreOnly?: boolean },
): Promise<Map<string, (number | null)[]>> {
  return loadLists(
    scope,
    [`pw AS (${powerSql(scope, ctypes, options.vreOnly ? ` AND m.${vre()}` : "")})`],
    `SELECT ${options.byCarrier ? "carrier" : "'all'"} AS key, snapshot, sum(p) AS v FROM pw GROUP BY ALL`,
    true,
  );
}

/** Stored energy per snapshot (MWh), per carrier: Store e, StorageUnit state_of_charge. */
export function loadStateOfCharge(
  scope: LevelQueryScope,
  ctype: "Store" | "StorageUnit",
  carrierLike: string | null,
): Promise<Map<string, (number | null)[]>> {
  const attribute = ctype === "Store" ? "e" : "state_of_charge";
  const filter = carrierLike === null ? "" : ` AND carrier ILIKE ${sqlString(carrierLike)}`;
  return loadLists(
    scope,
    [
      `s AS (SELECT entity, carrier FROM members WHERE ctype = ${sqlString(ctype)}${filter})`,
      `vals AS (${attributeValuesSql(scope, attribute, "entity", "SELECT entity AS key, entity AS subject FROM s")})`,
    ],
    `SELECT s.carrier AS key, v.snapshot, sum(v.value) AS v FROM vals v JOIN s ON s.entity = v.key GROUP BY ALL`,
    true,
  );
}

/** The mean marginal price over the level's buses (AC ones, unless the level is one bus) per snapshot. */
export async function loadMeanPrice(scope: LevelQueryScope): Promise<(number | null)[] | null> {
  const lists = await loadLists(
    scope,
    [
      `vals AS (${attributeValuesSql(scope, "marginal_price", "bus", `SELECT bus AS key, bus AS subject FROM (${levelBusesSql(scope, scope.level.kind !== "bus")})`)})`,
    ],
    `SELECT 'price' AS key, snapshot, avg(value) AS v FROM vals GROUP BY snapshot`,
  );
  return lists.get("price") ?? null;
}

// ------------------------------------------------------------ Statistics: bars

export interface CategoryValue {
  category: string | null;
  carrier: string | null;
  value: number;
}

/** Capacity (MW, MWh for stores) per carrier or per location (largest 12) of the level's members of `ctypes` (all when null). */
export async function loadCapacity(
  scope: LevelQueryScope,
  options: { ctypes: string[] | null; by: "carrier" | "location"; optimised: boolean },
): Promise<CategoryValue[]> {
  const cap = options.optimised ? "coalesce(capacity_opt, capacity)" : "capacity";
  const ctypes = options.ctypes ? `AND ctype IN (${options.ctypes.map(sqlString).join(", ")})` : "";
  const rows = await loadRows<CategoryValue>(
    scope,
    `
    SELECT ${options.by} AS category, ${options.by === "carrier" ? "carrier" : "NULL::VARCHAR"} AS carrier, sum(${cap})::DOUBLE AS value
    FROM members WHERE capacity IS NOT NULL ${ctypes}
    GROUP BY ALL HAVING sum(${cap}) > 0
    ORDER BY value DESC
    ${options.by === "location" ? "LIMIT 12" : ""}`,
  );
  return rows.map((row) => ({ ...row, value: Number(row.value) }));
}

/** The 12 locations with the highest summed load (MW) in the window. */
export async function loadPeakByLocation(scope: LevelQueryScope): Promise<CategoryValue[]> {
  const rows = await loadRows<CategoryValue>(
    scope,
    `,
    l AS (SELECT entity, coalesce(location, '(no location)') AS location FROM members WHERE ctype = 'Load'),
    vals AS (${attributeValuesSql(scope, "p_set", "entity", "SELECT entity AS key, entity AS subject FROM l")}),
    per AS (SELECT l.location, v.snapshot, sum(v.value) AS load FROM vals v JOIN l ON l.entity = v.key GROUP BY ALL)
    SELECT location AS category, NULL::VARCHAR AS carrier, max(load)::DOUBLE AS value FROM per GROUP BY location
    ORDER BY value DESC LIMIT 12`,
  );
  return rows.map((row) => ({ ...row, value: Number(row.value) }));
}

export interface LineRow {
  entity: string;
  capacity: number | null;
  length: number | null;
  /** Mean |p0| over the window ÷ capacity, in a run result. */
  loading: number | null;
}

/** The level's lines: capacity, length and, in a run result, mean loading over the window. */
export async function loadLines(
  scope: LevelQueryScope,
  options: { optimised: boolean },
): Promise<LineRow[]> {
  const cap = options.optimised ? "coalesce(e.capacity_opt, e.capacity)" : "e.capacity";
  const loading = options.optimised
    ? `(SELECT avg(abs(p.value)) FROM ${N("attributes.p")} p JOIN ${N("properties.connection")} c ON c.connection = p.connection AND c.role = 'input'
        WHERE p.connection.entity = e.entity AND ${spanCondition("p.snapshot", scope.period, scope.timeWindow)}) / nullif(${cap}, 0)`
    : "NULL::DOUBLE";
  const rows = await loadRows<LineRow>(
    scope,
    `
    SELECT e.entity, ${cap}::DOUBLE AS capacity, TRY_CAST(len.constant AS DOUBLE) AS length, ${loading} AS loading
    FROM members e
    LEFT JOIN ${N("manta.attribute_summary")} len ON len.dim = 'entity' AND len.label = e.entity AND len.attribute = 'length' AND len.bus IS NULL
    WHERE e.ctype = 'Line'`,
  );
  const number = (value: unknown) => (value === null || value === undefined ? null : Number(value));
  return rows.map((row) => ({
    entity: row.entity,
    capacity: number(row.capacity),
    length: number(row.length),
    loading: number(row.loading),
  }));
}

/**
 * Optimised capacity, or output summed over the window (energy: each
 * snapshot weighted by the hours it stands for), per category and carrier.
 * Categories: the component type, the bus, or the bus and type. Lines are
 * left out per bus; loads always; stores and lines from output. A link
 * counts at bus0, with what it delivers at its output.
 */
export async function loadOptimisedMix(
  scope: LevelQueryScope,
  what: "capacity" | "output",
  by: "ctype" | "bus" | "bus-ctype",
): Promise<CategoryValue[]> {
  const category =
    by === "ctype" ? "m.ctype" : by === "bus" ? "m.bus" : "m.bus || ' · ' || m.ctype";
  const busFilter = by === "ctype" ? "" : ` AND m.bus IN (${levelBusesSql(scope, false)})`;
  const body =
    what === "capacity"
      ? `
        SELECT ${category} AS category, m.carrier, sum(coalesce(m.capacity_opt, m.capacity))::DOUBLE AS value
        FROM members m
        WHERE m.ctype NOT IN ('Load', 'GlobalConstraint') AND m.capacity IS NOT NULL ${by === "ctype" ? "" : "AND m.ctype NOT IN ('Line', 'Transformer')"}${busFilter}
        GROUP BY ALL HAVING sum(coalesce(m.capacity_opt, m.capacity)) > 0`
      : `
        SELECT ${category} AS category, m.carrier, sum(greatest(CASE WHEN c.role = 'output' THEN -p.value ELSE p.value END, 0) * coalesce(w.value, 1))::DOUBLE AS value
        FROM ${N("attributes.p")} p
        JOIN ${N("properties.connection")} c ON c.connection = p.connection
        JOIN members m ON m.entity = p.connection.entity
        LEFT JOIN ${N("attributes.snapshot_weighting_generators")} w ON w.snapshot = p.snapshot
        WHERE ((m.ctype IN ('Generator', 'StorageUnit') AND c.role = 'attached') OR (m.ctype = 'Link' AND c.role = 'output'))
          AND ${spanCondition("p.snapshot", scope.period, scope.timeWindow)}${busFilter}
        GROUP BY ALL HAVING sum(greatest(CASE WHEN c.role = 'output' THEN -p.value ELSE p.value END, 0) * coalesce(w.value, 1)) > 0`;
  const rows = await loadRows<CategoryValue>(scope, body);
  return rows.map((row) => ({ ...row, value: Number(row.value) }));
}
