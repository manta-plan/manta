// The Analyse page's computed tables: our SQL that prepares a solved
// result's raw tables (attributes.p, marginal_price, p_nom_opt, …) into tables
// widgets can chart. Each is plain SQL over the record's views, written
// without a catalog (`attributes.p`, `dims.snapshot`); it runs against
// whichever result the page shows. They're listed, with their SQL and
// assumptions, under Computed in the Data panel.
//
// Every table has a numeric `value`, plus dimension columns. Some names mean
// more:
// - `period`: the investment period, as text; the period filter follows it.
// - `bus`: a location (site), as the map and the bus filter name them.
// - `carrier`: the carrier filter follows it.
// - `snapshot`: the record's snapshot (STRUCT(period, timestep)); a time axis.
// - `w`: the hours a snapshot stands for, to weight averages over time.

/**
 * How `value` adds up:
 * - energy: an amount per row (energy, emissions, money); sums over everything.
 * - power: a rate; sums over places and labels, then averages over time,
 *   weighted by the hours each snapshot stands for.
 * - price: averages over places and over time (hours-weighted).
 * - static: one value per period, no snapshots (capacity, annual costs).
 */
export type ValueKind = "energy" | "power" | "price" | "static";

export const VALUE_KINDS: { id: ValueKind; label: string; detail: string }[] = [
  {
    id: "energy",
    label: "Amount",
    detail: "Adds up over places and time: energy, emissions, money.",
  },
  {
    id: "power",
    label: "Rate",
    detail: "Adds up over places, averages over time (hours-weighted): power.",
  },
  { id: "price", label: "Price", detail: "Averages over places and time (hours-weighted)." },
  {
    id: "static",
    label: "Per period",
    detail: "One value per period, no snapshots: capacity, annual costs.",
  },
];

export interface ResultQuery {
  /** The SQL name widgets read it by: FROM supply. */
  name: string;
  label: string;
  description: string;
  /** Unit of `value`. */
  unit: string;
  /** What `value` measures, for axis names: "Supply". */
  valueLabel: string;
  kind: ValueKind;
  sql: string;
  /** Output columns besides `value` and `w`, in order. */
  columns: string[];
  /** Whether the output has `w` (hours per snapshot). */
  weighted: boolean;
}

export interface BuiltInQuery extends ResultQuery {
  builtIn: true;
  /** Choices baked into the definition that change its numbers. */
  assumptions: string[];
}

// ------------------------------------------------------------ Shared SQL

/** Each snapshot, its period (as text) and the hours it stands for. */
const SNAPSHOTS = `SELECT s.snapshot, CAST(s.snapshot.period AS VARCHAR) AS period, coalesce(w.value, 1) AS w
    FROM dims.snapshot s
    LEFT JOIN attributes.snapshot_weighting_generators w ON w.snapshot = s.snapshot`;

/** Power (MW) at an entity's own bus, or at a link's (or line's) input, with its type, carrier and location. */
const flows = (
  ctypes: string[],
) => `SELECT p.connection, p.connection.entity AS entity, e.ctype, e.carrier, bl.location AS bus, p.snapshot, p.value AS p
    FROM attributes.p p
    JOIN properties.connection pc ON pc.connection = p.connection
    JOIN properties.entity e ON e.entity = p.connection.entity
    JOIN manta.bus_location bl ON bl.bus = p.connection.bus
    WHERE e.ctype IN (${ctypes.map((ctype) => `'${ctype}'`).join(", ")})
      AND pc.role = CASE e.ctype WHEN 'Link' THEN 'input' WHEN 'Line' THEN 'input' ELSE 'attached' END
      AND NOT bl.virtual`;

/** An entity's location: where it's attached, or a link's input. */
const LOCATIONS = `SELECT pc.connection.entity AS entity, any_value(bl.location) AS bus
    FROM properties.connection pc
    JOIN manta.bus_location bl ON bl.bus = pc.connection.bus
    WHERE pc.role IN ('attached', 'input') AND NOT bl.virtual
    GROUP BY 1`;

/** The periods each entity is active in: build_year ≤ period < build_year + lifetime, and `active`. */
const ACTIVE = `SELECT e.entity, CAST(y.period AS VARCHAR) AS period
    FROM properties.entity e
    CROSS JOIN (SELECT DISTINCT snapshot.period AS period FROM dims.snapshot) y
    LEFT JOIN attributes.build_year b ON b.entity = e.entity
    LEFT JOIN attributes.lifetime l ON l.entity = e.entity
    LEFT JOIN attributes.active a ON a.entity = e.entity
    WHERE coalesce(b.value, 0) <= y.period
      AND y.period < coalesce(b.value, 0) + coalesce(l.value, 'inf'::DOUBLE)
      AND coalesce(a.value, true)`;

/** Optimised capacity: p_nom_opt, s_nom_opt for lines, e_nom_opt for stores. */
const NOMINAL = `SELECT entity, value FROM attributes.p_nom_opt
    UNION ALL SELECT entity, value FROM attributes.s_nom_opt
    UNION ALL SELECT entity, value FROM attributes.e_nom_opt`;

/** Annualised costs (€/a) per period, entity type, carrier and location. */
const COSTS = `WITH t AS (
    ${SNAPSHOTS}
  ), x AS (
    ${flows(["Generator", "StorageUnit", "Store", "Link"])}
  )
  -- Capex: capital_cost × optimised capacity, for what's active in the period.
  SELECT a.period, l.bus, e.ctype AS component, e.carrier, 'Capex' AS cost_type, cc.value * n.value AS value
  FROM attributes.capital_cost cc
  JOIN (${NOMINAL}) n ON n.entity = cc.entity
  JOIN properties.entity e ON e.entity = cc.entity
  JOIN (${ACTIVE}) a ON a.entity = cc.entity
  JOIN (${LOCATIONS}) l ON l.entity = cc.entity
  UNION ALL
  -- Opex: marginal_cost × power × hours (a series, or a constant for every snapshot).
  SELECT t.period, x.bus, x.ctype, x.carrier, 'Opex', sum(coalesce(ms.value, mk.value, 0) * x.p * t.w)
  FROM x
  JOIN t ON t.snapshot = x.snapshot
  LEFT JOIN attributes.marginal_cost ms ON ms.entity = x.entity AND ms.snapshot = x.snapshot
  LEFT JOIN attributes.marginal_cost mk ON mk.entity = x.entity AND mk.snapshot IS NULL
  GROUP BY ALL`;

// ------------------------------------------------------------ Built-in queries

const TIMED = ["period", "snapshot", "bus", "carrier"];
const ACTIVE_RULE =
  "An asset counts in a period when build_year ≤ period < build_year + lifetime (and `active`).";
const PER_YEAR = "Each period's snapshot weights add up to a year, so energies are a year's.";
const LOCATION = "`bus` is the location (site) of the bus, as the map and the bus filter name it.";

const builtIn = (query: Omit<BuiltInQuery, "builtIn" | "sql"> & { sql: string }): BuiltInQuery => ({
  builtIn: true,
  ...query,
  sql: query.sql.trim(),
});

export const BUILT_IN_QUERIES: BuiltInQuery[] = [
  builtIn({
    name: "supply",
    label: "Supply",
    description:
      "Energy generators supply, per carrier: power × the hours each snapshot stands for.",
    unit: "TWh",
    valueLabel: "Supply",
    kind: "energy",
    columns: TIMED,
    weighted: true,
    assumptions: [
      "Generators only; storage discharge and link output are not supply here.",
      PER_YEAR,
      LOCATION,
    ],
    sql: `
WITH g AS (
    ${flows(["Generator"])}
), t AS (
    ${SNAPSHOTS}
)
SELECT t.period, t.snapshot, g.bus, g.carrier, g.p * t.w / 1e6 AS value, t.w
FROM g JOIN t ON t.snapshot = g.snapshot`,
  }),
  builtIn({
    name: "withdrawal",
    label: "Withdrawal",
    description: "Energy loads draw, per carrier: power × the hours each snapshot stands for.",
    unit: "TWh",
    valueLabel: "Withdrawal",
    kind: "energy",
    columns: TIMED,
    weighted: true,
    assumptions: [
      "Loads only; storage charging and electrolysis are not withdrawal here.",
      PER_YEAR,
      LOCATION,
    ],
    sql: `
WITH g AS (
    ${flows(["Load"])}
), t AS (
    ${SNAPSHOTS}
)
SELECT t.period, t.snapshot, g.bus, g.carrier, g.p * t.w / 1e6 AS value, t.w
FROM g JOIN t ON t.snapshot = g.snapshot`,
  }),
  builtIn({
    name: "dispatch",
    label: "Dispatch",
    description: "Power output of generators and storage units per carrier, at each snapshot.",
    unit: "GW",
    valueLabel: "Power",
    kind: "power",
    columns: TIMED,
    weighted: true,
    assumptions: [
      "Generators and storage units; storage charging is negative. Links and stores are left out.",
      LOCATION,
    ],
    sql: `
WITH g AS (
    ${flows(["Generator", "StorageUnit"])}
), t AS (
    ${SNAPSHOTS}
)
SELECT t.period, t.snapshot, g.bus, g.carrier, g.p / 1e3 AS value, t.w
FROM g JOIN t ON t.snapshot = g.snapshot`,
  }),
  builtIn({
    name: "load",
    label: "Load",
    description: "Power loads draw at each snapshot, per carrier: the demand dispatch has to meet.",
    unit: "GW",
    valueLabel: "Load",
    kind: "power",
    columns: TIMED,
    weighted: true,
    assumptions: ["Loads only: storage charging and electrolysis are not load here.", LOCATION],
    sql: `
WITH g AS (
    ${flows(["Load"])}
), t AS (
    ${SNAPSHOTS}
)
SELECT t.period, t.snapshot, g.bus, g.carrier, g.p / 1e3 AS value, t.w
FROM g JOIN t ON t.snapshot = g.snapshot`,
  }),
  builtIn({
    name: "prices",
    label: "Bus prices",
    description: "Marginal price at each bus, per bus carrier (AC, H2, …).",
    unit: "€/MWh",
    valueLabel: "Price",
    kind: "price",
    columns: TIMED,
    weighted: true,
    assumptions: [
      "Averages over buses are plain; over time they weight each snapshot by its hours.",
      LOCATION,
    ],
    sql: `
WITH t AS (
    ${SNAPSHOTS}
)
SELECT t.period, t.snapshot, bl.location AS bus, bl.carrier, m.value, t.w
FROM attributes.marginal_price m
JOIN manta.bus_location bl ON bl.bus = m.bus
JOIN t ON t.snapshot = m.snapshot
WHERE NOT bl.virtual`,
  }),
  builtIn({
    name: "capacity",
    label: "Installed capacity",
    description: "Optimised power capacity (p_nom_opt) of what is active in each period.",
    unit: "GW",
    valueLabel: "Capacity",
    kind: "static",
    columns: ["period", "bus", "component", "carrier"],
    weighted: false,
    assumptions: [
      ACTIVE_RULE,
      "Power capacity only: stores (energy, e_nom_opt) and lines (s_nom_opt) are left out.",
      "A link counts at its input.",
    ],
    sql: `
SELECT a.period, l.bus, e.ctype AS component, e.carrier, n.value / 1e3 AS value
FROM attributes.p_nom_opt n
JOIN properties.entity e ON e.entity = n.entity
JOIN (
    ${ACTIVE}
) a ON a.entity = n.entity
JOIN (
    ${LOCATIONS}
) l ON l.entity = n.entity`,
  }),
  builtIn({
    name: "energy_capacity",
    label: "Storage energy capacity",
    description: "Optimised energy capacity of stores (e_nom_opt) active in each period.",
    unit: "GWh",
    valueLabel: "Energy capacity",
    kind: "static",
    columns: ["period", "bus", "component", "carrier"],
    weighted: false,
    assumptions: [
      ACTIVE_RULE,
      "Stores only (e_nom_opt). A storage unit's energy is its power × max_hours, and is not counted here.",
    ],
    sql: `
SELECT a.period, l.bus, e.ctype AS component, e.carrier, n.value / 1e3 AS value
FROM attributes.e_nom_opt n
JOIN properties.entity e ON e.entity = n.entity
JOIN (
    ${ACTIVE}
) a ON a.entity = n.entity
JOIN (
    ${LOCATIONS}
) l ON l.entity = n.entity`,
  }),
  builtIn({
    name: "curtailment",
    label: "Curtailment",
    description:
      "Available energy that was not used: optimised capacity × p_max_pu − power, × hours.",
    unit: "TWh",
    valueLabel: "Curtailment",
    kind: "energy",
    columns: TIMED,
    weighted: true,
    assumptions: [
      "Generators with a p_max_pu series only (wind, solar, run of river).",
      ACTIVE_RULE,
      PER_YEAR,
    ],
    sql: `
WITH g AS (
    ${flows(["Generator"])}
), t AS (
    ${SNAPSHOTS}
)
SELECT t.period, t.snapshot, g.bus, g.carrier, greatest(n.value * pu.value - g.p, 0) * t.w / 1e6 AS value, t.w
FROM g
JOIN attributes.p_max_pu pu ON pu.entity = g.entity AND pu.snapshot = g.snapshot
JOIN attributes.p_nom_opt n ON n.entity = g.entity
JOIN t ON t.snapshot = g.snapshot
JOIN (
    ${ACTIVE}
) a ON a.entity = g.entity AND a.period = t.period`,
  }),
  builtIn({
    name: "component_costs",
    label: "Costs by component",
    description: "Annualised capital and operational expenditure per component type.",
    unit: "bn €/a",
    valueLabel: "Cost",
    kind: "static",
    columns: ["period", "bus", "component", "cost_type"],
    weighted: false,
    assumptions: [
      "Capex = capital_cost (annualised) × optimised capacity (p_nom_opt, s_nom_opt, e_nom_opt) of what is active in the period.",
      "Opex = marginal_cost × power × hours, for generators, storage units, stores and links (at their input).",
      ACTIVE_RULE,
    ],
    sql: `
SELECT period, bus, component, cost_type, sum(value) / 1e9 AS value
FROM (
  ${COSTS}
)
GROUP BY ALL`,
  }),
  builtIn({
    name: "carrier_costs",
    label: "Costs by carrier",
    description: "Annualised capital and operational expenditure per carrier.",
    unit: "bn €/a",
    valueLabel: "Cost",
    kind: "static",
    columns: ["period", "bus", "carrier", "cost_type"],
    weighted: false,
    assumptions: [
      "Capex = capital_cost (annualised) × optimised capacity (p_nom_opt, s_nom_opt, e_nom_opt) of what is active in the period.",
      "Opex = marginal_cost × power × hours, for generators, storage units, stores and links (at their input).",
      ACTIVE_RULE,
    ],
    sql: `
SELECT period, bus, carrier, cost_type, sum(value) / 1e9 AS value
FROM (
  ${COSTS}
)
GROUP BY ALL`,
  }),
  builtIn({
    name: "emissions",
    label: "Emissions",
    description:
      "CO2 from generators' fuel: power ÷ efficiency × the carrier's co2_emissions, × hours.",
    unit: "Mt CO2",
    valueLabel: "Emissions",
    kind: "energy",
    columns: TIMED,
    weighted: true,
    assumptions: [
      "Generators only, by their carrier's co2_emissions (t/MWh of fuel).",
      "Efficiency is the series at each snapshot, else the constant, else 1.",
      PER_YEAR,
    ],
    sql: `
WITH g AS (
    ${flows(["Generator"])}
), t AS (
    ${SNAPSHOTS}
)
SELECT t.period, t.snapshot, g.bus, g.carrier, g.p / coalesce(es.value, ek.value, 1) * co.value * t.w / 1e6 AS value, t.w
FROM g
JOIN attributes.co2_emissions co ON co.carrier = g.carrier AND co.value <> 0
JOIN t ON t.snapshot = g.snapshot
LEFT JOIN attributes.efficiency es ON es.connection = g.connection AND es.snapshot = g.snapshot
LEFT JOIN attributes.efficiency ek ON ek.connection = g.connection AND ek.snapshot IS NULL`,
  }),
];

export function builtInQuery(name: string): BuiltInQuery | undefined {
  return BUILT_IN_QUERIES.find((query) => query.name === name);
}

// ------------------------------------------------------------ Running a query's SQL

/** The record's schemas a query reads; each name is qualified with the result's catalog. */
const SCHEMAS = ["attributes", "dims", "properties", "manta"];
const SCHEMA_REFERENCE = new RegExp(`(?<![\\w."'])(${SCHEMAS.join("|")})\\.`, "g");

/** The SQL with every record view in `catalog`: `attributes.p` → `<catalog>.attributes.p`. Strings and comments are left alone. */
export function qualify(sql: string, catalog: string): string {
  return splitCode(sql)
    .map((part) => (part.code ? part.text.replace(SCHEMA_REFERENCE, `${catalog}.$1.`) : part.text))
    .join("");
}

/** The SQL in code and non-code (string literals, comments) parts. */
function splitCode(sql: string): { text: string; code: boolean }[] {
  const parts: { text: string; code: boolean }[] = [];
  let index = 0;
  let start = 0;
  const push = (end: number, code: boolean) =>
    end > start && parts.push({ text: sql.slice(start, end), code });
  while (index < sql.length) {
    const rest = sql.slice(index);
    const quote = rest[0] === "'" || rest[0] === '"';
    const dollar = rest.startsWith("$$");
    const lineComment = rest.startsWith("--");
    const blockComment = rest.startsWith("/*");
    if (!quote && !dollar && !lineComment && !blockComment) {
      index++;
      continue;
    }
    push(index, true);
    start = index;
    if (dollar)
      index = sql.indexOf("$$", index + 2) === -1 ? sql.length : sql.indexOf("$$", index + 2) + 2;
    else if (quote) {
      const mark = rest[0];
      let end = index + 1;
      while (end < sql.length && !(sql[end] === mark && sql[end + 1] !== mark))
        end += sql[end] === mark ? 2 : 1;
      index = end + 1;
    } else if (lineComment)
      index = sql.indexOf("\n", index) === -1 ? sql.length : sql.indexOf("\n", index);
    else index = sql.indexOf("*/", index) === -1 ? sql.length : sql.indexOf("*/", index) + 2;
    push(index, false);
    start = index;
  }
  push(sql.length, true);
  return parts;
}

/** The computed tables `sql` reads by name (FROM supply, JOIN prices). */
function referencedQueries(sql: string, queries: ResultQuery[]): ResultQuery[] {
  const code = splitCode(sql)
    .filter((part) => part.code)
    .map((part) => part.text)
    .join(" ");
  // Names the SQL defines itself (WITH g AS (…)) are its own CTEs, not tables.
  const local = new Set(
    [
      ...code.matchAll(
        /\b([a-z_][a-z0-9_]*)\s+as\s*(?:not\s+materialized\s*|materialized\s*)?\(/gi,
      ),
    ].map((match) => match[1].toLowerCase()),
  );
  return queries.filter(
    (query) =>
      !local.has(query.name) && new RegExp(`\\b(from|join)\\s+${query.name}\\b`, "i").test(code),
  );
}

/**
 * The SQL ready to run for one result: computed tables it reads by name
 * become CTEs before it, and every record view is qualified with the
 * result's catalog. (Computed tables read only the record, never each other.)
 */
export function compileQuerySql(
  sql: string,
  catalog: string,
  queries: ResultQuery[] = BUILT_IN_QUERIES,
): string {
  const body = sql.trim().replace(/;\s*$/, "");
  const used = referencedQueries(body, queries);
  if (used.length === 0) return qualify(body, catalog);
  // Inlined, not materialised, so a widget's filters reach into each table.
  const ctes = used.map(
    (query) => `${query.name} AS NOT MATERIALIZED (\n${query.sql.trim().replace(/;\s*$/, "")}\n)`,
  );
  return qualify(`WITH ${ctes.join(",\n")}\n${body}`, catalog);
}

// ------------------------------------------------------------ The output contract

export interface OutputColumn {
  name: string;
  type: string;
}

export interface OutputCheck {
  /** Dimension columns (not value or w), in order. */
  columns: string[];
  weighted: boolean;
  problems: string[];
  /** What the special columns switch on. */
  notes: string[];
}

/** Whether a query's output fits the contract, and what it enables. */
export function checkOutput(output: OutputColumn[], kind: ValueKind): OutputCheck {
  const problems: string[] = [];
  const notes: string[] = [];
  const byName = new Map(output.map((column) => [column.name, column.type.toUpperCase()]));
  const numeric = (type: string | undefined) =>
    !!type &&
    /^(DOUBLE|FLOAT|REAL|DECIMAL|HUGEINT|BIGINT|INTEGER|SMALLINT|TINYINT|UBIGINT|UINTEGER|USMALLINT|UTINYINT)/.test(
      type,
    );
  if (!byName.has("value"))
    problems.push("No `value` column: select the number to chart AS value.");
  else if (!numeric(byName.get("value")))
    problems.push(`\`value\` is ${byName.get("value")}; it must be a number.`);
  if (byName.has("w") && !numeric(byName.get("w")))
    problems.push(`\`w\` is ${byName.get("w")}; it must be a number of hours.`);
  const snapshot = byName.get("snapshot");
  if (snapshot && !/^STRUCT\(.*period.*timestep/i.test(snapshot.replaceAll('"', "")))
    problems.push(
      "`snapshot` must be the record's snapshot (dims.snapshot), a STRUCT(period, timestep).",
    );
  if (kind === "static" && snapshot)
    problems.push(
      "A per-period query has no `snapshot`: aggregate over the snapshots first, or pick another value kind.",
    );
  if (kind !== "static" && !snapshot)
    notes.push("No `snapshot`: the values are treated as one per row, with no time axis.");
  const duplicates = output
    .map((column) => column.name)
    .filter((name, index, names) => names.indexOf(name) !== index);
  if (duplicates.length > 0)
    problems.push(`Column names must be unique: ${[...new Set(duplicates)].join(", ")}.`);
  if (byName.has("period"))
    notes.push('`period`: follows the period filter, and "All periods" shows an average year.');
  if (byName.has("bus")) notes.push("`bus`: follows the bus filter, and can be drawn on the map.");
  if (byName.has("carrier")) notes.push("`carrier`: follows the carrier filter.");
  if (snapshot)
    notes.push(
      byName.has("w")
        ? "`snapshot` and `w`: a time axis, with averages weighted by hours."
        : "`snapshot` without `w`: averages over time count every snapshot the same.",
    );
  const columns = output
    .map((column) => column.name)
    .filter((name) => name !== "value" && name !== "w");
  return { columns, weighted: byName.has("w"), problems, notes };
}
