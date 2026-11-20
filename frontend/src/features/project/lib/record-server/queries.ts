import { fetchApi, recordCatalog, serverName, serverQuery, sqlName, sqlString } from "./client";
import type {
  AttributeSpec,
  Branch,
  Carrier,
  DimensionLabel,
  EntityAttribute,
  EntityConnection,
  EntityCount,
  EntityDetail,
  EntityListItem,
  EntityValue,
  LabelDetail,
  Location,
  LocationGraphRows,
  LocationZone,
  Manifest,
  RecordInfo,
  Region,
  ScenarioChange,
  ScenarioChangeSummary,
  ScenarioChangeValue,
  SeriesPoint,
} from "./types";

// Typed reads of the record, in the active scenario's catalog (serverName).
// Every read runs on the server (serverQuery): records open on demand, and the
// browser's attached `r` only lists the catalogs that existed when it
// attached. It also means only the result travels.

export function openRecord(id: string): Promise<RecordInfo> {
  return fetchApi<RecordInfo>(`/api/records/${encodeURIComponent(id)}/open`, "POST");
}

export function getCarriers(): Promise<Carrier[]> {
  return serverQuery<Carrier>(
    `SELECT carrier, color, nice_name AS "niceName" FROM ${serverName("properties.carrier")}`,
  );
}

export function getEntityCounts(): Promise<EntityCount[]> {
  return serverQuery<EntityCount>(
    `SELECT ctype, carrier, count(*) AS entities FROM ${serverName("properties.entity")} GROUP BY ALL ORDER BY ALL`,
  );
}

export function getLocations(): Promise<Location[]> {
  return serverQuery<Location>(`FROM ${serverName("manta.locations")} ORDER BY location`);
}

export function getLocationZones(): Promise<LocationZone[]> {
  return serverQuery<LocationZone>(`FROM ${serverName("manta.location_zones")}`);
}

// What the map draws: branches whose ends are at two different real locations.
export function getMapBranches(): Promise<Branch[]> {
  return serverQuery<Branch>(
    `SELECT DISTINCT entity, ctype, carrier, location0, location1 FROM ${serverName("manta.branches")} WHERE scope = 'between'`,
  );
}

export function getRegions(): Promise<Region[]> {
  return serverQuery<Region>(
    `SELECT entity, bus, location, wkt FROM ${serverName("manta.regions")}`,
  );
}

export function getEntities(ctype: string, carrier: string | null): Promise<EntityListItem[]> {
  return serverQuery<EntityListItem>(`
    SELECT e.entity,
           coalesce(a.location, b.location0, g.location) AS location,
           coalesce(b.outputs, []) AS outputs
    FROM ${serverName("properties.entity")} e
    LEFT JOIN ${serverName("manta.attached")} a USING (entity)
    LEFT JOIN (SELECT entity, any_value(location0) AS location0, list(DISTINCT location1 ORDER BY location1) AS outputs
               FROM ${serverName("manta.branches")} GROUP BY entity) b USING (entity)
    LEFT JOIN ${serverName("manta.regions")} g USING (entity)
    WHERE e.ctype = ${sqlString(ctype)} AND e.carrier IS NOT DISTINCT FROM ${carrier === null ? "NULL" : sqlString(carrier)}
    ORDER BY e.entity`);
}

// The manifest default for one entity: a `default_by` rule on its ctype wins.
export function defaultFor(spec: AttributeSpec, ctype: string): unknown {
  const byCtype = spec.default_by["entity.ctype"];
  return byCtype && ctype in byCtype ? byCtype[ctype] : spec.default;
}

const usedByCtype = new Map<string, Promise<Set<string>>>();

// Attributes this ctype has values for somewhere in the record: where an
// entity without a value reads the default, rather than the attribute not
// applying to it at all (the manifest doesn't say which ctype uses what).
// Per scenario: a scenario may store values the base case leaves default.
function attributesUsedBy(ctype: string): Promise<Set<string>> {
  const key = `${recordCatalog() ?? ""}\n${ctype}`;
  let used = usedByCtype.get(key);
  if (!used) {
    used = serverQuery<{ attribute: string }>(
      `SELECT attribute FROM ${serverName("manta.ctype_attributes")} WHERE ctype = ${sqlString(ctype)}`,
    ).then((rows) => new Set(rows.map((row) => row.attribute)));
    usedByCtype.set(key, used);
  }
  return used;
}

export async function getEntity(entity: string, manifest: Manifest): Promise<EntityDetail | null> {
  const id = sqlString(entity);
  const [[properties], connections, values] = await Promise.all([
    serverQuery<Record<string, unknown>>(
      `FROM ${serverName("properties.entity")} WHERE entity = ${id}`,
    ),
    serverQuery<EntityConnection>(`
      SELECT c.connection.bus AS bus, c.role, b.location, b.carrier AS "busCarrier"
      FROM ${serverName("properties.connection")} c JOIN ${serverName("manta.bus_location")} b ON b.bus = c.connection.bus
      WHERE c.connection.entity = ${id}
      ORDER BY c.role, c.connection.bus`),
    serverQuery<{
      attribute: string;
      bus: string | null;
      constant: string | null;
      seriesRows: number;
    }>(`
      SELECT attribute, bus, constant, series_rows AS "seriesRows"
      FROM ${serverName("manta.attribute_summary")} WHERE dim = 'entity' AND label = ${id}`),
  ]);
  if (!properties) return null;

  const ctype = String(properties.ctype);
  const used = await attributesUsedBy(ctype);
  const stored = new Set(values.map((row) => row.attribute));
  const attributes: EntityAttribute[] = values
    .filter((row) => manifest.attributes[row.attribute])
    .map((row) => ({
      name: row.attribute,
      spec: manifest.attributes[row.attribute],
      bus: row.bus,
      value: row.constant,
      isDefault: false,
      seriesRows: row.seriesRows,
    }));
  for (const name of used) {
    const spec = manifest.attributes[name];
    if (stored.has(name) || !spec) continue;
    const fallback = defaultFor(spec, ctype);
    attributes.push({
      name,
      spec,
      bus: null,
      value: fallback == null ? null : String(fallback),
      isDefault: true,
      seriesRows: 0,
    });
  }
  attributes.sort(
    (a, b) => a.name.localeCompare(b.name) || (a.bus ?? "").localeCompare(b.bus ?? ""),
  );
  return { entity, properties, connections, attributes };
}

// One attribute's snapshot values for an entity (and, for attributes over
// `connection`, one of its outputs), with each snapshot's period and timestep.
export function getSeries(
  attribute: string,
  spec: AttributeSpec,
  entity: string,
  bus: string | null,
): Promise<SeriesPoint[]> {
  const subject = spec.dims.includes("connection")
    ? `a.connection.entity = ${sqlString(entity)}${bus ? ` AND a.connection.bus = ${sqlString(bus)}` : ""}`
    : `a.entity = ${sqlString(entity)}`;
  return serverQuery<SeriesPoint>(`
    SELECT a.snapshot, s.period, strftime(s.timestep, '%Y-%m-%d %H:%M') AS timestep, TRY_CAST(a.value AS DOUBLE) AS value
    FROM ${serverName(`attributes.${sqlName(attribute)}`)} a
    LEFT JOIN ${serverName("properties.snapshot")} s USING (snapshot)
    WHERE ${subject} AND a.snapshot IS NOT NULL
    ORDER BY a.snapshot`);
}

// A dimension's labels with their properties, where the record has any.
export async function getDimension(name: string, info: RecordInfo): Promise<DimensionLabel[]> {
  const hasProperties = info.views.properties?.includes(name);
  const rows = await serverQuery<Record<string, unknown>>(
    `SELECT *, ${sqlName(name)}::VARCHAR AS "__label" FROM ${serverName(`${hasProperties ? "properties" : "dims"}.${sqlName(name)}`)}`,
  );
  return rows.map((row) => {
    const { [name]: value, __label: label, ...properties } = row;
    return { label: String(label), value, properties };
  });
}

function summaryAttributes(
  rows: { attribute: string; bus: string | null; constant: string | null; seriesRows: number }[],
  manifest: Manifest,
): EntityAttribute[] {
  return rows
    .filter((row) => manifest.attributes[row.attribute])
    .map((row) => ({
      name: row.attribute,
      spec: manifest.attributes[row.attribute],
      bus: row.bus,
      value: row.constant,
      isDefault: false,
      seriesRows: row.seriesRows,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// Per scenario, the attributes it changes: what the Scenarios panel lists.
export function getScenarioChanges(): Promise<ScenarioChangeSummary[]> {
  return serverQuery<ScenarioChangeSummary>(`
    SELECT scenario, attribute, dim, count(DISTINCT (label, bus)) AS subjects,
           sum(series_rows) AS "seriesRows", median(ratio) AS ratio
    FROM ${serverName("manta.scenario_changes")} GROUP BY ALL ORDER BY scenario, attribute`);
}

// One change in full: each entity or bus, with where it is. Every catalog of
// a record holds the changes of all its scenarios; the joins read the shown
// scenario's network.
export function getScenarioChange(scenario: string, attribute: string): Promise<ScenarioChange[]> {
  return serverQuery<ScenarioChange>(`
    SELECT c.dim, c.label, c.bus, c.before, c.after, c.series_rows AS "seriesRows", c.ratio,
           e.ctype, e.carrier, coalesce(a.location, br.location0, bl.location) AS location
    FROM ${serverName("manta.scenario_changes")} c
    LEFT JOIN ${serverName("properties.entity")} e ON c.dim = 'entity' AND e.entity = c.label
    LEFT JOIN ${serverName("manta.attached")} a ON c.dim = 'entity' AND a.entity = c.label
    LEFT JOIN (SELECT entity, any_value(location0) AS location0 FROM ${serverName("manta.branches")} GROUP BY entity) br
      ON c.dim = 'entity' AND br.entity = c.label
    LEFT JOIN ${serverName("manta.bus_location")} bl ON c.dim = 'bus' AND bl.bus = c.label
    WHERE c.scenario = ${sqlString(scenario)} AND c.attribute = ${sqlString(attribute)}
    ORDER BY c.label, c.bus`);
}

// Every value one scenario changes, keyed by changeKey: the markers in the
// drawers and the entity table.
export async function getScenarioChangeValues(
  scenario: string,
): Promise<Map<string, ScenarioChangeValue>> {
  const rows = await serverQuery<
    ScenarioChangeValue & { attribute: string; dim: string; label: string; bus: string | null }
  >(`
    SELECT attribute, dim, label, bus, before, after, series_rows AS "seriesRows", ratio
    FROM ${serverName("manta.scenario_changes")} WHERE scenario = ${sqlString(scenario)}`);
  return new Map(
    rows.map(({ attribute, dim, label, bus, ...value }) => [
      changeKey(attribute, dim, label, bus),
      value,
    ]),
  );
}

export function changeKey(
  attribute: string,
  dim: string,
  label: string,
  bus: string | null,
): string {
  return [attribute, dim, label, bus ?? ""].join("\n");
}

// A label of a dimension other than entity (a bus, a carrier, a snapshot, …):
// its properties and the attributes stored over it.
export async function getLabelDetail(
  dim: string,
  label: string,
  info: RecordInfo,
): Promise<LabelDetail> {
  const [labels, values] = await Promise.all([
    info.views.properties?.includes(dim)
      ? serverQuery<Record<string, unknown>>(
          `FROM ${serverName(`properties.${sqlName(dim)}`)} WHERE ${sqlName(dim)}::VARCHAR = ${sqlString(label)}`,
        )
      : Promise.resolve([]),
    serverQuery<{
      attribute: string;
      bus: string | null;
      constant: string | null;
      seriesRows: number;
    }>(`
      SELECT attribute, bus, constant, series_rows AS "seriesRows"
      FROM ${serverName("manta.attribute_summary")} WHERE dim = ${sqlString(dim)} AND label = ${sqlString(label)}`),
  ]);
  const { [dim]: value, ...properties } = labels[0] ?? {};
  // A connection's values are summarised per entity and bus, not per label.
  if (dim === "connection" && value && typeof value === "object") {
    const { entity, bus } = value as { entity: string; bus: string };
    const rows = await serverQuery<{
      attribute: string;
      bus: string | null;
      constant: string | null;
      seriesRows: number;
    }>(`
      SELECT attribute, bus, constant, series_rows AS "seriesRows"
      FROM ${serverName("manta.attribute_summary")} WHERE dim = 'entity' AND label = ${sqlString(entity)} AND bus = ${sqlString(bus)}`);
    return {
      dim,
      label,
      properties: { entity, bus, ...properties },
      attributes: summaryAttributes(rows, info.manifest),
    };
  }
  return { dim, label, properties, attributes: summaryAttributes(values, info.manifest) };
}

// Every stored value of the entities of one ctype (and carrier), for the table.
export function getEntityValues(ctype: string, carrier: string | null): Promise<EntityValue[]> {
  return serverQuery<EntityValue>(`
    SELECT s.label AS entity, s.attribute, s.bus, s.constant, s.series_rows AS "seriesRows"
    FROM ${serverName("manta.attribute_summary")} s JOIN ${serverName("properties.entity")} e ON e.entity = s.label
    WHERE s.dim = 'entity' AND e.ctype = ${sqlString(ctype)}
      AND e.carrier IS NOT DISTINCT FROM ${carrier === null ? "NULL" : sqlString(carrier)}`);
}

// What a location (or a zone's locations) holds: its buses, what's attached
// to them, and every branch with an end there.
export async function getLocationGraph(locations: string[]): Promise<LocationGraphRows> {
  const inside = locations.map(sqlString).join(", ");
  const capacity = (attribute: string) => `
    LEFT JOIN ${serverName("manta.attribute_summary")} c
      ON c.dim = 'entity' AND c.label = x.entity AND c.bus IS NULL AND c.attribute = ${attribute}`;
  const [buses, attached, branches] = await Promise.all([
    serverQuery<LocationGraphRows["buses"][number]>(
      `SELECT bus, carrier, location FROM ${serverName("manta.bus_location")} WHERE location IN (${inside}) ORDER BY bus`,
    ),
    serverQuery<LocationGraphRows["attached"][number]>(`
      SELECT x.entity, x.ctype, x.carrier, x.bus, TRY_CAST(c.constant AS DOUBLE) AS capacity
      FROM ${serverName("manta.attached")} x ${capacity("CASE x.ctype WHEN 'Store' THEN 'e_nom' ELSE 'p_nom' END")}
      WHERE x.location IN (${inside})`),
    serverQuery<LocationGraphRows["branches"][number]>(`
      SELECT x.entity, x.ctype, x.carrier, x.bus0, x.bus1, x.location0, x.location1, x.scope,
             TRY_CAST(c.constant AS DOUBLE) AS capacity
      FROM ${serverName("manta.branches")} x ${capacity("CASE x.ctype WHEN 'Link' THEN 'p_nom' ELSE 's_nom' END")}
      WHERE x.location0 IN (${inside}) OR x.location1 IN (${inside})`),
  ]);
  return { buses, attached, branches };
}
