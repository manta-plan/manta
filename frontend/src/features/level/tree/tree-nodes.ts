import { busLabel, entityLabel } from "../../project/lib/record-format";
import type { LoadedRecord } from "../../project/store/types";
import { ALL_ENTITIES, ALL_LOCATIONS, type Level } from "../level";
import {
  treeBuses,
  treeLeaves,
  type LeafFilter,
  type TreeCount,
  type TreeLocation,
} from "./tree-queries";

// The sidebar tree: two roots, each row a level of the page.
//
//   Entities → type → carrier → entity     (types without carriers skip a level)
//   Locations → location → bus → entity     (a two-ended entity sits at both ends)
//
// Counts and lists are of entities active in the investment period. A
// node's entities (and a location's buses) are fetched when it opens; until
// then it holds placeholder children (skeleton rows), so the tree can show
// it as openable. A node lists at most LEAF_CAP entities, then a row saying
// how many more the table has.

// The zone levels worth offering: those that actually group locations
// (busmap_all keeps one zone per location, which is just nodal).
function zoneLevels(record: LoadedRecord): { level: string; zones: number }[] {
  const zonesByLevel = new Map<string, Set<string>>();
  for (const { level, zone } of record.zones)
    zonesByLevel.set(level, (zonesByLevel.get(level) ?? new Set()).add(zone));
  return [...zonesByLevel]
    .map(([level, zones]) => ({ level, zones: zones.size }))
    .filter(({ zones }) => zones < record.locations.length)
    .sort((a, b) => a.zones - b.zones);
}

export type TreeNodeKind =
  | "category"
  | "ctype"
  | "carrier"
  | "location"
  | "bus"
  | "entity"
  | "more"
  | "placeholder";

export interface TreeNode {
  id: string;
  name: string;
  kind: TreeNodeKind;
  detail?: string;
  color?: string | null;
  title?: string;
  /** A location's region. */
  pill?: string;
  children?: TreeNode[];
  /** The level a click opens. */
  level?: Level;
  /** Fetches this node's children on first open. */
  lazy?: LazyChildren;
  /** A placeholder standing in for children still loading: its place among them. */
  skeleton?: number;
}

export type LazyChildren =
  | { kind: "leaves"; filter: LeafFilter; level: Level }
  | { kind: "buses"; location: string };

export const ENTITIES_ID = "entities";
export const LOCATIONS_ID = "locations";

export function ctypeNodeId(ctype: string): string {
  return `ctype:${ctype}`;
}

export function carrierNodeId(ctype: string, carrier: string | null): string {
  return `carrier:${ctype}:${carrier ?? ""}`;
}

export function locationNodeId(location: string): string {
  return `location:${location}`;
}

export function busNodeId(bus: string, location: string): string {
  return `bus:${bus}@${location}`;
}

// Rows shown for a folder's children until they load.
const SKELETON_ROWS = 3;

function loadingRows(parentId: string): TreeNode[] {
  return Array.from({ length: SKELETON_ROWS }, (_, index) => ({
    id: `${parentId}/loading-${index}`,
    name: "Loading…",
    kind: "placeholder" as const,
    skeleton: index,
  }));
}

/** Each location's region, at the zone level with the fewest zones above one; empty without one. */
export function regionsOf(record: LoadedRecord): Map<string, string> {
  const level = zoneLevels(record).find(({ zones }) => zones > 1)?.level;
  if (!level) return new Map();
  return new Map(
    record.zones.filter((zone) => zone.level === level).map((zone) => [zone.location, zone.zone]),
  );
}

const count = (value: number) => value.toLocaleString();

/** Lazy nodes get their loaded children (lazy themselves, a location's buses), or skeleton rows. */
function attach(nodes: TreeNode[], loaded: Record<string, TreeNode[]>): TreeNode[] {
  return nodes.map((node) => {
    if (node.lazy)
      return { ...node, children: attach(loaded[node.id] ?? loadingRows(node.id), loaded) };
    return node.children ? { ...node, children: attach(node.children, loaded) } : node;
  });
}

export function buildTree(
  record: LoadedRecord,
  counts: TreeCount[],
  locations: TreeLocation[],
  loaded: Record<string, TreeNode[]>,
): TreeNode[] {
  const byCtype = new Map<string, TreeCount[]>();
  for (const item of counts) byCtype.set(item.ctype, [...(byCtype.get(item.ctype) ?? []), item]);

  const ctypes = [...byCtype]
    .map(([ctype, items]) => ({
      ctype,
      items,
      total: items.reduce((sum, item) => sum + item.entities, 0),
    }))
    .sort((a, b) => b.total - a.total)
    .map(({ ctype, items, total }): TreeNode => {
      const withoutCarrier = items.length === 1 && items[0].carrier === null;
      const level: Level = { kind: "component", ctype };
      const node: TreeNode = {
        id: ctypeNodeId(ctype),
        name: ctype,
        kind: "ctype",
        detail: count(total),
        level,
      };
      if (withoutCarrier)
        return { ...node, lazy: { kind: "leaves", filter: { kind: "type", ctype }, level } };
      const carriers = [...items]
        .sort((a, b) => b.entities - a.entities)
        .map(({ carrier, entities }): TreeNode => {
          const known = carrier ? record.carriers[carrier] : undefined;
          // Entities without a carrier have no level of their own: their type's.
          const carrierLevel: Level =
            carrier === null ? level : { kind: "carrier", ctype, carrier };
          return {
            id: carrierNodeId(ctype, carrier),
            name: known?.niceName || carrier || "(no carrier)",
            title: carrier ?? undefined,
            kind: "carrier",
            color: known?.color,
            detail: count(entities),
            level: carrierLevel,
            lazy: { kind: "leaves", filter: { kind: "type", ctype, carrier }, level: carrierLevel },
          };
        });
      return { ...node, children: carriers };
    });

  const regions = regionsOf(record);
  const byRegion = (a?: string, b?: string) =>
    a === b ? 0 : a === undefined ? 1 : b === undefined ? -1 : a.localeCompare(b);
  const locationNodes = locations
    .map((item) => ({ ...item, region: regions.get(item.location) }))
    .sort((a, b) => byRegion(a.region, b.region) || a.location.localeCompare(b.location))
    .map(({ location, entities, region }): TreeNode => ({
      id: locationNodeId(location),
      name: location,
      kind: "location",
      pill: region,
      detail: count(entities),
      level: { kind: "location", location },
      lazy: { kind: "buses", location },
    }));

  const total = counts.reduce((sum, item) => sum + item.entities, 0);
  return attach(
    [
      {
        id: ENTITIES_ID,
        name: "Entities",
        kind: "category",
        detail: count(total),
        level: ALL_ENTITIES,
        children: ctypes,
      },
      {
        id: LOCATIONS_ID,
        name: "Locations",
        kind: "category",
        detail: count(locations.length),
        level: ALL_LOCATIONS,
        children: locationNodes,
      },
    ],
    loaded,
  );
}

/** A node's children, active in `period`: a location's buses, or a node's entities (capped). */
export async function loadChildren(
  lazy: LazyChildren,
  parentId: string,
  record: LoadedRecord,
  period: string,
): Promise<TreeNode[]> {
  if (lazy.kind === "buses") {
    const buses = await treeBuses(period, lazy.location);
    return buses.map(({ bus, carrier, entities }): TreeNode => {
      const level: Level = { kind: "bus", bus, location: lazy.location };
      return {
        id: busNodeId(bus, lazy.location),
        name: busLabel(bus, lazy.location, carrier ?? ""),
        title: bus,
        kind: "bus",
        color: carrier ? record.carriers[carrier]?.color : null,
        detail: count(entities),
        level,
        lazy: { kind: "leaves", filter: { kind: "bus", bus }, level },
      };
    });
  }

  const leaves = await treeLeaves(period, lazy.filter);
  const underBus = lazy.filter.kind === "bus";
  const nodes: TreeNode[] = leaves.map((leaf) => ({
    // An entity can sit under several nodes (both ends of a line): ids are per parent.
    id: `${parentId}/${leaf.entity}`,
    name: entityLabel(leaf.entity, leaf.location),
    title: leaf.entity,
    kind: "entity",
    color: leaf.carrier ? record.carriers[leaf.carrier]?.color : null,
    detail: underBus ? leaf.ctype : undefined,
    level: { kind: "entity", entity: leaf.entity },
  }));
  const more = (leaves[0]?.total ?? 0) - leaves.length;
  if (more > 0)
    nodes.push({
      id: `${parentId}/more`,
      name: `${count(more)} more in the table`,
      title: "Open the table to see them all",
      kind: "more",
      level: lazy.level,
    });
  return nodes;
}
