// The record as the app sees it: datarecord's manifest, and the rows the
// server's `manta` views return (server/app/manta_views.py).

export interface AttributeSpec {
  default: unknown;
  // e.g. { 'entity.ctype': { Load: -1 } }: a default per category label.
  default_by: Record<string, Record<string, unknown>>;
  unit: string | null;
  description: string;
  dtype?: string;
  // Set instead of dtype when the value is a label of that dim.
  one_of?: string;
  dims: string[];
  breakpoints?: boolean;
}

export interface DimensionSpec {
  dtype: string;
  unit: string | null;
  description: string;
}

export interface Manifest {
  id: string;
  version: number;
  dimensions: Record<string, DimensionSpec>;
  attributes: Record<string, AttributeSpec>;
  // Per dim: its property columns, specified like attributes.
  properties: Record<string, Record<string, AttributeSpec>>;
  meta: Record<string, unknown>;
}

// A store's named revision: a scenario (inputs, or edits to them) or a run
// result (a solve of its parent).
export interface Revision {
  name: string;
  id: string;
  parent: string | null;
  kind: "scenario" | "result";
  label: string;
  description: string;
  // The server catalog a scenario is read from (`<record>__<scenario>`);
  // null for a run result, which isn't served yet.
  catalog: string | null;
}

// One attribute a scenario changes, over how many entities or buses.
export interface ScenarioChangeSummary {
  scenario: string;
  attribute: string;
  dim: string;
  subjects: number;
  seriesRows: number;
  ratio: number | null;
}

// One entity's (or bus's) changed value; a series change has no before or
// after, only how many rows changed and their median ratio.
export interface ScenarioChange {
  dim: string;
  label: string;
  bus: string | null;
  before: string | null;
  after: string | null;
  seriesRows: number;
  ratio: number | null;
  ctype: string | null;
  carrier: string | null;
  location: string | null;
}

// A changed value as the drawers and the entity table mark it.
export type ScenarioChangeValue = Pick<ScenarioChange, "before" | "after" | "seriesRows" | "ratio">;

// An open record: what the app needs to query it.
export interface RecordInfo {
  id: string;
  label: string;
  description: string;
  // The scenario shown when none is chosen: the base case.
  defaultScenario: string;
  revisions: Revision[];
  // Schema → view names, in the default scenario's catalog.
  views: Record<string, string[]>;
  manifest: Manifest;
}

export interface Carrier {
  carrier: string;
  color: string | null;
  niceName: string | null;
}

export interface EntityCount {
  ctype: string;
  // Null for ctypes without carriers (Shape, Transformer).
  carrier: string | null;
  entities: number;
}

// A real place: buses of every carrier at one site, named after its AC bus.
export interface Location {
  location: string;
  x: number;
  y: number;
  buses: number;
  carriers: string[];
}

export interface LocationZone {
  level: string;
  location: string;
  zone: string;
}

// One input → output pair of a line, link or transformer between two locations.
export interface Branch {
  entity: string;
  ctype: string;
  carrier: string | null;
  location0: string;
  location1: string;
}

export interface Region {
  entity: string;
  bus: string | null;
  location: string | null;
  wkt: string;
}

export interface EntityListItem {
  entity: string;
  // Where it is: its bus's location, a branch's input location, or a Shape's.
  location: string | null;
  // A branch's output locations.
  outputs: string[];
}

export interface EntityConnection {
  bus: string;
  role: string;
  location: string;
  busCarrier: string;
}

export interface EntityAttribute {
  name: string;
  spec: AttributeSpec;
  // Set for attributes over `connection`: the output bus the value is for.
  bus: string | null;
  // The stored constant (as text), or the manifest default when isDefault.
  value: string | null;
  isDefault: boolean;
  // Rows that vary by snapshot; 0 for a constant.
  seriesRows: number;
}

export interface EntityDetail {
  entity: string;
  properties: Record<string, unknown>;
  connections: EntityConnection[];
  attributes: EntityAttribute[];
}

export interface SeriesPoint {
  snapshot: number;
  period: number | null;
  timestep: string | null;
  value: number | null;
}

export interface DimensionLabel {
  // DuckDB's text for the label: unique even for a struct label such as a
  // connection's {entity, bus}, and what getLabelDetail matches on.
  label: string;
  value: unknown;
  properties: Record<string, unknown>;
}

export interface LabelDetail {
  dim: string;
  label: string;
  properties: Record<string, unknown>;
  attributes: EntityAttribute[];
}

// One stored attribute value of one entity, for the entity table.
export interface EntityValue {
  entity: string;
  attribute: string;
  bus: string | null;
  constant: string | null;
  seriesRows: number;
}

export interface GraphBus {
  bus: string;
  carrier: string;
  location: string;
}

export interface GraphAttached {
  entity: string;
  ctype: string;
  carrier: string | null;
  bus: string;
  // p_nom (e_nom for stores) when stored as a constant.
  capacity: number | null;
}

export interface GraphBranch {
  entity: string;
  ctype: string;
  carrier: string | null;
  bus0: string;
  bus1: string;
  location0: string;
  location1: string;
  scope: "within" | "between" | "virtual";
  // p_nom for links, s_nom for lines and transformers, when stored.
  capacity: number | null;
}

export interface LocationGraphRows {
  buses: GraphBus[];
  attached: GraphAttached[];
  branches: GraphBranch[];
}
