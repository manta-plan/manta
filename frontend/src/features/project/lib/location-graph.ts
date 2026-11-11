import { busLabel, entityLabel, formatCapacity } from "./record-format";
import type { GraphAttached, GraphBranch, LocationGraphRows } from "./record-server/types";

// What happens inside a place (a location, or a zone's locations), as a graph.
//
// - aggregated (the map popup): one node per bus carrier, links between two
//   of them merged into one edge, everything outside collapsed per
//   neighbouring place, and what's attached to a bus folded into its label.
// - full (the bottom drawer): every bus, and every attached entity and
//   branch as its own node, filterable by carrier and ctype.

export type GraphMode = "aggregated" | "full";

export interface GraphNodeModel {
  id: string;
  shape: "circle" | "diamond";
  label: string;
  title: string;
  color: string;
  textColor: string;
  // Set on nodes that stand for one entity or one bus.
  entity?: string;
  bus?: string;
}

export interface GraphEdgeModel {
  id: string;
  source: string;
  target: string;
  label?: string;
  color: string;
}

export interface GraphModel {
  nodes: GraphNodeModel[];
  edges: GraphEdgeModel[];
}

export interface GraphContext {
  // The locations that make up this place.
  inside: Set<string>;
  // Real locations; any other location (EU) is a copper plate, not a place.
  real: Set<string>;
  // Where an outside location belongs: its zone when zonal, else itself.
  placeOf: (location: string) => string;
  carrierColor: (carrier: string | null) => string | null;
  carrierName: (carrier: string | null) => string;
}

const NEUTRAL = "#64748b";
const REMOTE = "#475569";
const VIRTUAL = "#334155";
const SHORT_CTYPE: Record<string, string> = {
  Generator: "gen",
  Load: "load",
  Store: "store",
  StorageUnit: "storage",
};

// Light text on dark fills, dark on light.
function textOn(color: string): string {
  const hex = color.replace("#", "");
  if (hex.length !== 6) return "#ffffff";
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#0f172a" : "#ffffff";
}

function node(
  id: string,
  shape: GraphNodeModel["shape"],
  label: string,
  title: string,
  color: string,
  extra: Partial<GraphNodeModel> = {},
): GraphNodeModel {
  return { id, shape, label, title, color, textColor: textOn(color), ...extra };
}

export function placeNodeId(place: string): string {
  return `place:${place}`;
}

export function entityNodeId(entity: string): string {
  return `entity:${entity}`;
}

// The node an end of a branch lands on, given the inside buses' node ids.
function endNode(
  bus: string,
  location: string,
  insideBusNode: Map<string, string>,
  context: GraphContext,
  nodes: Map<string, GraphNodeModel>,
): string {
  const inside = insideBusNode.get(bus);
  if (inside) return inside;
  const place = context.real.has(location) ? context.placeOf(location) : location;
  const id = placeNodeId(place);
  if (!nodes.has(id)) {
    const virtual = !context.real.has(location);
    nodes.set(
      id,
      node(
        id,
        "circle",
        place,
        virtual ? `${place}: a copper plate, not a place` : place,
        virtual ? VIRTUAL : REMOTE,
      ),
    );
  }
  return id;
}

function attachedSummary(attached: GraphAttached[]): string {
  const counts = new Map<string, number>();
  for (const item of attached) counts.set(item.ctype, (counts.get(item.ctype) ?? 0) + 1);
  return [...counts].map(([ctype, count]) => `${count} ${SHORT_CTYPE[ctype] ?? ctype}`).join(" · ");
}

export function buildAggregated(rows: LocationGraphRows, context: GraphContext): GraphModel {
  const nodes = new Map<string, GraphNodeModel>();
  const insideBusNode = new Map<string, string>();
  const busCarrier = new Map(rows.buses.map((bus) => [bus.bus, bus.carrier]));
  const attachedByCarrier = new Map<string, GraphAttached[]>();
  for (const item of rows.attached) {
    const carrier = busCarrier.get(item.bus) ?? "";
    attachedByCarrier.set(carrier, [...(attachedByCarrier.get(carrier) ?? []), item]);
  }
  for (const bus of rows.buses) {
    const id = `carrier:${bus.carrier}`;
    insideBusNode.set(bus.bus, id);
    if (nodes.has(id)) continue;
    const summary = attachedSummary(attachedByCarrier.get(bus.carrier) ?? []);
    const name = context.carrierName(bus.carrier);
    nodes.set(
      id,
      node(
        id,
        "circle",
        summary ? `${name}\n${summary}` : name,
        `${name} bus${summary ? `: ${summary}` : ""}`,
        context.carrierColor(bus.carrier) ?? NEUTRAL,
      ),
    );
  }

  const edges = new Map<
    string,
    { source: string; target: string; carriers: Set<string>; count: number; capacity: number }
  >();
  const seen = new Set<string>();
  for (const branch of rows.branches) {
    const source = endNode(branch.bus0, branch.location0, insideBusNode, context, nodes);
    const target = endNode(branch.bus1, branch.location1, insideBusNode, context, nodes);
    if (source === target) continue;
    const id = `${source}->${target}`;
    const edge = edges.get(id) ?? {
      source,
      target,
      carriers: new Set<string>(),
      count: 0,
      capacity: 0,
    };
    edge.carriers.add(branch.carrier ?? branch.ctype);
    // A link with several outputs is one link: count it once per edge.
    const key = `${id}|${branch.entity}`;
    if (!seen.has(key)) {
      seen.add(key);
      edge.count += 1;
      edge.capacity += branch.capacity ?? 0;
    }
    edges.set(id, edge);
  }

  return {
    nodes: [...nodes.values()],
    edges: [...edges].map(([id, edge]) => {
      const single = edge.carriers.size === 1 ? [...edge.carriers][0] : null;
      const name = single ? context.carrierName(single) : `${edge.count} branches`;
      const capacity = edge.capacity > 0 ? ` · ${formatCapacity(edge.capacity)}` : "";
      return {
        id,
        source: edge.source,
        target: edge.target,
        label: `${name}${single && edge.count > 1 ? ` ×${edge.count}` : ""}${capacity}`,
        color: (single && context.carrierColor(single)) || NEUTRAL,
      };
    }),
  };
}

export interface GraphFilter {
  carriers: Set<string>;
  ctypes: Set<string>;
}

export function entityPasses(
  item: { ctype: string; carrier: string | null },
  hidden: GraphFilter,
): boolean {
  return !hidden.ctypes.has(item.ctype) && !hidden.carriers.has(item.carrier ?? "");
}

export function buildFull(
  rows: LocationGraphRows,
  context: GraphContext,
  hidden: GraphFilter,
): GraphModel {
  const nodes = new Map<string, GraphNodeModel>();
  const insideBusNode = new Map<string, string>();
  for (const bus of rows.buses) {
    const id = `bus:${bus.bus}`;
    insideBusNode.set(bus.bus, id);
    const name = busLabel(bus.bus, bus.location, bus.carrier);
    nodes.set(
      id,
      node(id, "circle", name, bus.bus, context.carrierColor(bus.carrier) ?? NEUTRAL, {
        bus: bus.bus,
      }),
    );
  }
  const busLocation = new Map(rows.buses.map((bus) => [bus.bus, bus.location]));
  const edges: GraphEdgeModel[] = [];
  const color = (carrier: string | null) => context.carrierColor(carrier) ?? NEUTRAL;

  for (const item of rows.attached) {
    if (!entityPasses(item, hidden)) continue;
    const id = entityNodeId(item.entity);
    const capacity = item.capacity
      ? `\n${formatCapacity(item.capacity, item.ctype === "Store" ? "MWh" : "MW")}`
      : "";
    nodes.set(
      id,
      node(
        id,
        "diamond",
        `${SHORT_CTYPE[item.ctype] ?? item.ctype}${capacity}`,
        `${item.ctype} · ${context.carrierName(item.carrier)}\n${entityLabel(item.entity, busLocation.get(item.bus) ?? null)}`,
        color(item.carrier),
        { entity: item.entity },
      ),
    );
    const bus = `bus:${item.bus}`;
    // Generation flows into the bus, demand out of it; storage both ways.
    edges.push(
      item.ctype === "Load"
        ? { id: `${bus}->${id}`, source: bus, target: id, color: color(item.carrier) }
        : { id: `${id}->${bus}`, source: id, target: bus, color: color(item.carrier) },
    );
  }

  const byEntity = new Map<string, GraphBranch[]>();
  for (const branch of rows.branches)
    byEntity.set(branch.entity, [...(byEntity.get(branch.entity) ?? []), branch]);
  for (const [entity, outputs] of byEntity) {
    const first = outputs[0];
    if (!entityPasses(first, hidden)) continue;
    const id = entityNodeId(entity);
    const capacity = first.capacity ? `\n${formatCapacity(first.capacity)}` : "";
    nodes.set(
      id,
      node(
        id,
        "diamond",
        `${context.carrierName(first.carrier ?? first.ctype)}${capacity}`,
        `${first.ctype} · ${context.carrierName(first.carrier)}\n${entity}`,
        color(first.carrier),
        { entity },
      ),
    );
    const input = endNode(first.bus0, first.location0, insideBusNode, context, nodes);
    edges.push({ id: `${input}->${id}`, source: input, target: id, color: color(first.carrier) });
    for (const output of outputs) {
      const target = endNode(output.bus1, output.location1, insideBusNode, context, nodes);
      edges.push({
        id: `${id}->${target}:${output.bus1}`,
        source: id,
        target,
        color: color(first.carrier),
      });
    }
  }

  return { nodes: [...nodes.values()], edges };
}
