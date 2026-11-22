import { useMemo, useState } from "react";
import clsx from "clsx";
import { LuMaximize2 } from "react-icons/lu";
import {
  buildAggregated,
  buildFull,
  entityNodeId,
  entityPasses,
  type GraphFilter,
  type GraphNodeModel,
} from "../lib/location-graph";
import { entityLabel, formatCapacity } from "../lib/record-format";
import { useGraphContext, useLocationGraphRows } from "../lib/use-location-graph";
import type { RecordItem } from "../store/types";
import { useProjectStore } from "../store/project-store";
import { LocationGraph } from "./location-graph";

function Message({ children }: { children: string }) {
  return (
    <div className="text-surface-400 flex h-full items-center justify-center text-[12px]">
      {children}
    </div>
  );
}

// What a graph node click opens: the entity, or the bus as a label.
function nodeItem(
  node: GraphNodeModel,
  entityKinds: Map<string, { ctype: string; carrier: string | null; location: string }>,
): RecordItem | null {
  if (node.entity) {
    const known = entityKinds.get(node.entity);
    return known
      ? {
          kind: "entity",
          entity: node.entity,
          ctype: known.ctype,
          carrier: known.carrier,
          locations: [known.location],
        }
      : null;
  }
  if (node.bus) return { kind: "label", dim: "bus", label: node.bus };
  return null;
}

// Step 1, the map popup: the place at a glance.
export function LocationPopupGraph({
  title,
  locations,
  onOpen,
}: {
  title: string;
  locations: string[];
  onOpen: () => void;
}) {
  const { rows, error } = useLocationGraphRows(locations);
  const context = useGraphContext(locations);
  const model = useMemo(
    () => (rows && context ? buildAggregated(rows, context) : null),
    [context, rows],
  );

  return (
    <div className="flex flex-col gap-1.5 px-1 py-0.5">
      <div className="flex items-center gap-2 pr-5">
        <span className="text-surface-50 min-w-0 truncate text-[12px] font-semibold" title={title}>
          {title}
        </span>
        {rows && (
          <span className="text-surface-400 shrink-0 text-[10px] tracking-wide uppercase">
            {rows.buses.length} buses ·{" "}
            {rows.attached.length + new Set(rows.branches.map((branch) => branch.entity)).size}{" "}
            entities
          </span>
        )}
        <button
          type="button"
          onClick={onOpen}
          className="border-surface-600 text-surface-200 hover:bg-surface-700 ml-auto flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium outline-none"
        >
          <LuMaximize2 size={11} />
          Open
        </button>
      </div>
      <div className="h-[420px] w-[600px]">
        {error ? (
          <Message>{error}</Message>
        ) : !model ? (
          <Message>Loading…</Message>
        ) : (
          <LocationGraph model={model} />
        )}
      </div>
    </div>
  );
}

function Chips({
  label,
  values,
  hidden,
  onToggle,
  colorOf,
  nameOf,
}: {
  label: string;
  values: string[];
  hidden: Set<string>;
  onToggle: (value: string) => void;
  colorOf?: (value: string) => string | null;
  nameOf?: (value: string) => string;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1">
      <span className="text-surface-500 mr-1 text-[10px] font-semibold tracking-wide uppercase">
        {label}
      </span>
      {values.map((value) => {
        const color = colorOf?.(value);
        return (
          <button
            key={value}
            type="button"
            onClick={() => onToggle(value)}
            className={clsx(
              "flex h-6 items-center gap-1 rounded-full border px-2 text-[11px] outline-none",
              hidden.has(value)
                ? "border-surface-700 text-surface-500 line-through"
                : "border-surface-600 text-surface-200 hover:bg-surface-700",
            )}
          >
            {color && <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />}
            {nameOf?.(value) ?? (value || "—")}
          </button>
        );
      })}
    </div>
  );
}

function toggled(set: Set<string>, value: string): Set<string> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

// Step 2, the bottom drawer: everything at the place, as a graph that can be
// filtered and a table beside it; picking in one highlights in the other.
export function LocationView({ locations }: { locations: string[] }) {
  const openItemDrawer = useProjectStore((s) => s.openItemDrawer);
  const { rows, error } = useLocationGraphRows(locations);
  const context = useGraphContext(locations);
  const [hidden, setHidden] = useState<GraphFilter>({ carriers: new Set(), ctypes: new Set() });
  const [selected, setSelected] = useState<string | null>(null);

  // Every entity at the place, attached or a branch with an end here.
  const entities = useMemo(() => {
    if (!rows) return [];
    const busLocation = new Map(rows.buses.map((bus) => [bus.bus, bus.location]));
    const attached = rows.attached.map((item) => ({
      entity: item.entity,
      ctype: item.ctype,
      carrier: item.carrier,
      bus: item.bus,
      location: busLocation.get(item.bus) ?? "",
      capacity: item.capacity,
    }));
    const branches = new Map<string, (typeof attached)[number]>();
    for (const branch of rows.branches) {
      if (branches.has(branch.entity)) continue;
      const insideEnd = context?.inside.has(branch.location0) ? branch.bus0 : branch.bus1;
      branches.set(branch.entity, {
        entity: branch.entity,
        ctype: branch.ctype,
        carrier: branch.carrier,
        bus: insideEnd,
        location: busLocation.get(insideEnd) ?? branch.location0,
        capacity: branch.capacity,
      });
    }
    return [...attached, ...branches.values()].sort(
      (a, b) =>
        a.ctype.localeCompare(b.ctype) ||
        (a.carrier ?? "").localeCompare(b.carrier ?? "") ||
        a.entity.localeCompare(b.entity),
    );
  }, [context, rows]);
  const entityKinds = useMemo(
    () => new Map(entities.map((item) => [item.entity, item])),
    [entities],
  );
  const carriers = useMemo(
    () => [...new Set(entities.map((item) => item.carrier ?? ""))].sort(),
    [entities],
  );
  const ctypes = useMemo(() => [...new Set(entities.map((item) => item.ctype))].sort(), [entities]);
  const visible = entities.filter((item) => entityPasses(item, hidden));

  const model = useMemo(
    () => (rows && context ? buildFull(rows, context, hidden) : null),
    [context, hidden, rows],
  );

  if (error) return <Message>{error}</Message>;
  if (!rows || !context || !model) return <Message>Loading…</Message>;

  const pick = (item: RecordItem | null, nodeId: string) => {
    setSelected(nodeId);
    if (item) openItemDrawer(item);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-surface-700 bg-surface-800 flex shrink-0 flex-col gap-1.5 border-b px-3 py-2">
        <Chips
          label="ctype"
          values={ctypes}
          hidden={hidden.ctypes}
          onToggle={(value) =>
            setHidden((current) => ({ ...current, ctypes: toggled(current.ctypes, value) }))
          }
        />
        <Chips
          label="carrier"
          values={carriers}
          hidden={hidden.carriers}
          onToggle={(value) =>
            setHidden((current) => ({ ...current, carriers: toggled(current.carriers, value) }))
          }
          colorOf={(value) => context.carrierColor(value || null)}
          nameOf={(value) => (value ? context.carrierName(value) : "—")}
        />
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <LocationGraph
            model={model}
            dense
            highlightedId={selected}
            onNodeClick={(node) => pick(nodeItem(node, entityKinds), node.id)}
          />
        </div>
        <div className="border-surface-700 w-[440px] shrink-0 overflow-y-auto border-l">
          <table className="w-full border-collapse text-[12px]">
            <thead className="bg-surface-800 text-surface-400 sticky top-0 text-left">
              <tr>
                <th className="border-surface-600 border-b px-3 py-1.5 font-medium">Entity</th>
                <th className="border-surface-600 border-b px-3 py-1.5 font-medium">ctype</th>
                <th className="border-surface-600 border-b px-3 py-1.5 text-right font-medium">
                  Capacity
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => {
                const nodeId = entityNodeId(item.entity);
                return (
                  <tr
                    key={item.entity}
                    onClick={() =>
                      pick(
                        {
                          kind: "entity",
                          entity: item.entity,
                          ctype: item.ctype,
                          carrier: item.carrier,
                          locations: [item.location],
                        },
                        nodeId,
                      )
                    }
                    className={clsx(
                      "cursor-default",
                      selected === nodeId
                        ? "bg-accent-600/25 text-surface-50"
                        : "text-surface-200 hover:bg-surface-700/60",
                    )}
                  >
                    <td
                      className="border-surface-700/60 max-w-[220px] border-b px-3 py-1"
                      title={item.entity}
                    >
                      <span className="flex items-center gap-1.5">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{
                            backgroundColor: context.carrierColor(item.carrier) ?? "transparent",
                          }}
                        />
                        <span className="truncate">{entityLabel(item.entity, item.location)}</span>
                      </span>
                    </td>
                    <td className="border-surface-700/60 text-surface-400 border-b px-3 py-1">
                      {item.ctype}
                    </td>
                    <td className="border-surface-700/60 text-surface-400 border-b px-3 py-1 text-right tabular-nums">
                      {item.capacity
                        ? formatCapacity(item.capacity, item.ctype === "Store" ? "MWh" : "MW")
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
