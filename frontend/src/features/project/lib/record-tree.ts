import { busLabel, entityLabel, formatTimestamp } from "./record-format";
import { zoneOf } from "./record-geo";
import { getDimension, getEntities } from "./record-server/queries";
import type { LoadedRecord, RecordItem, Resolution } from "../store/types";

// The sidebar tree, in datarecord's terms:
//
//   Entities → ctype → carrier → entity     (ctypes without carriers skip a level)
//   Dimensions → dim → label                (bus grouped by location, or zone → location)
//
// Entities and labels are fetched when their parent opens; until then the
// parent holds one placeholder child, so the tree can show it as openable.

export type TreeNodeKind =
  | "category"
  | "ctype"
  | "carrier"
  | "dimension"
  | "group"
  | "entity"
  | "label"
  | "placeholder";

export interface TreeNode {
  id: string;
  name: string;
  kind: TreeNodeKind;
  detail?: string;
  color?: string | null;
  title?: string;
  children?: TreeNode[];
  // What a click opens in the item drawer.
  item?: RecordItem;
  // Fetches this node's children on first open.
  lazy?: LazyChildren;
  // Rows of the entity table this node can open.
  table?: { ctype: string; carrier: string | null };
}

export type LazyChildren =
  | { kind: "entities"; ctype: string; carrier: string | null }
  | { kind: "dimension"; dim: string };

export const ENTITIES_ID = "entities";
export const DIMENSIONS_ID = "dimensions";

export function entityNodeId(entity: string): string {
  return `entity:${entity}`;
}

export function entitiesNodeId(ctype: string, carrier: string | null): string {
  return carrier === null ? `ctype:${ctype}` : `carrier:${ctype}:${carrier}`;
}

function placeholder(parentId: string, name = "Loading…"): TreeNode {
  return { id: `${parentId}/placeholder`, name, kind: "placeholder" };
}

export function buildTree(record: LoadedRecord, loaded: Record<string, TreeNode[]>): TreeNode[] {
  const lazyChildren = (id: string) => loaded[id] ?? [placeholder(id)];
  const byCtype = new Map<string, { carrier: string | null; entities: number }[]>();
  for (const count of record.entityCounts)
    byCtype.set(count.ctype, [...(byCtype.get(count.ctype) ?? []), count]);

  const ctypes: TreeNode[] = [...byCtype]
    .map(([ctype, counts]) => ({
      ctype,
      counts,
      total: counts.reduce((sum, count) => sum + count.entities, 0),
    }))
    .sort((a, b) => b.total - a.total)
    .map(({ ctype, counts, total }) => {
      const withoutCarrier = counts.length === 1 && counts[0].carrier === null;
      const id = entitiesNodeId(ctype, null);
      return {
        id,
        name: ctype,
        kind: "ctype" as const,
        detail: total.toLocaleString(),
        table: withoutCarrier ? { ctype, carrier: null } : undefined,
        lazy: withoutCarrier ? { kind: "entities" as const, ctype, carrier: null } : undefined,
        children: withoutCarrier
          ? lazyChildren(id)
          : counts
              .sort((a, b) => b.entities - a.entities)
              .map(({ carrier, entities }) => {
                const carrierId = entitiesNodeId(ctype, carrier ?? "");
                const known = carrier ? record.carriers[carrier] : undefined;
                return {
                  id: carrierId,
                  name: known?.niceName || carrier || "(no carrier)",
                  title: carrier ?? undefined,
                  kind: "carrier" as const,
                  color: known?.color,
                  detail: entities.toLocaleString(),
                  table: { ctype, carrier },
                  lazy: { kind: "entities" as const, ctype, carrier },
                  children: lazyChildren(carrierId),
                };
              }),
      };
    });

  const dimensions: TreeNode[] = Object.keys(record.info.manifest.dimensions)
    .filter((dim) => dim !== "entity")
    .map((dim) => {
      const id = `dimension:${dim}`;
      return {
        id,
        name: dim,
        kind: "dimension" as const,
        title: record.info.manifest.dimensions[dim].description,
        lazy: { kind: "dimension" as const, dim },
        children: lazyChildren(id),
      };
    });

  return [
    { id: ENTITIES_ID, name: "Entities", kind: "category", children: ctypes },
    { id: DIMENSIONS_ID, name: "Dimensions", kind: "category", children: dimensions },
  ];
}

export async function loadChildren(
  lazy: LazyChildren,
  record: LoadedRecord,
  resolution: Resolution,
): Promise<TreeNode[]> {
  if (lazy.kind === "entities") {
    const entities = await getEntities(lazy.ctype, lazy.carrier);
    return entities.map((item) => ({
      id: entityNodeId(item.entity),
      name: entityLabel(item.entity, item.location),
      title: item.entity,
      kind: "entity",
      item: {
        kind: "entity",
        entity: item.entity,
        ctype: lazy.ctype,
        carrier: lazy.carrier,
        locations: [
          ...new Set(
            [item.location, ...item.outputs].filter((location): location is string =>
              Boolean(location),
            ),
          ),
        ],
      },
    }));
  }

  const { dim } = lazy;
  const labels = await getDimension(dim, record.info);
  const labelNode = (
    label: string,
    name: string,
    color?: string | null,
    detail?: string,
  ): TreeNode => ({
    id: `label:${dim}:${label}`,
    name,
    title: label,
    kind: "label",
    color,
    detail,
    item: { kind: "label", dim, label, ...(dim === "connection" ? { name } : {}) },
  });

  if (dim === "bus") {
    // ~1,170 buses at ~70 locations: group them, by zone first when zonal.
    const zones = zoneOf(record, resolution);
    const byLocation = new Map<string, TreeNode[]>();
    for (const { label, properties } of labels) {
      const location = String(properties.location ?? "");
      const carrier = String(properties.carrier ?? "");
      byLocation.set(location, [
        ...(byLocation.get(location) ?? []),
        labelNode(label, busLabel(label, location, carrier), record.carriers[carrier]?.color),
      ]);
    }
    const locationNodes = [...byLocation]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([location, buses]): TreeNode => ({
        id: `bus-location:${location}`,
        name: location,
        kind: "group",
        detail: String(buses.length),
        children: buses.sort((a, b) => a.name.localeCompare(b.name)),
      }));
    if (zones.size === 0) return locationNodes;
    const byZone = new Map<string, TreeNode[]>();
    for (const node of locationNodes) {
      const zone = zones.get(node.name) ?? "(no zone)";
      byZone.set(zone, [...(byZone.get(zone) ?? []), node]);
    }
    return [...byZone]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([zone, locations]) => ({
        id: `bus-zone:${zone}`,
        name: zone,
        kind: "group" as const,
        detail: String(locations.length),
        children: locations,
      }));
  }

  return labels.map(({ label, value, properties }) => {
    if (dim === "connection" && value && typeof value === "object") {
      const { entity, bus } = value as { entity: string; bus: string };
      return labelNode(
        label,
        `${entity} → ${bus}`,
        null,
        properties.role == null ? undefined : String(properties.role),
      );
    }
    if (dim === "carrier")
      return labelNode(label, String(properties.nice_name || label), record.carriers[label]?.color);
    if (dim === "snapshot")
      return labelNode(
        label,
        `${label} · ${properties.period ?? ""} · ${formatTimestamp(properties.timestep)}`,
      );
    if (dim === "timestep") return labelNode(label, formatTimestamp(value));
    return labelNode(label, label);
  });
}
