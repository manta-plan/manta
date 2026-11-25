import { useMemo, type ReactNode } from "react";
import { useLevelPage } from "../../level-page-context";
import { useLevelStore } from "../../level-store";
import { useBuses, type BusRow } from "../map-graph-data";
import { busCarrierOrder, useSchematic, type SchematicEntity } from "./graph-data";
import { shortId, useCarrierLook } from "./graph-look";
import { EntityShape, FOCUS, HALO, Hit, LINE } from "./graph-parts";
import { ZoomPanSvg } from "./zoom-pan-svg";

// One location's buses and what's on them. Buses sit in a row in the
// record's bus carrier order (first left, next right, …). Single-bus
// entities group by component and carrier on their bus: the first bus's on
// the left, the last's on the right, any middle one's above it. Links
// between the buses curve between them; lines and links to other locations
// run to their far buses along the bottom. Outside the focus (a bus or an
// entity) things fade. A group of one opens its entity; a larger one sets
// the table's Carrier filter.

const W = 660;
const H = 400;
const BUS_Y = 165;
const BUS_R = 30;
const BOTTOM_Y = 352;
const FADED = 0.22;
const NO_BUSES: BusRow[] = [];

interface Group {
  key: string;
  ctype: string;
  carrier: string | null;
  bus: string;
  bus1: string | null;
  items: SchematicEntity[];
}

function groupBy(entities: SchematicEntity[], key: (entity: SchematicEntity) => string): Group[] {
  const groups = new Map<string, Group>();
  for (const entity of entities) {
    const id = key(entity);
    const group = groups.get(id) ?? {
      key: id,
      ctype: entity.ctype,
      carrier: entity.carrier,
      bus: entity.bus ?? "",
      bus1: entity.bus1,
      items: [],
    };
    group.items.push(entity);
    groups.set(id, group);
  }
  return [...groups.values()];
}

export function BusSchematic({
  location,
  focusBus,
  focusEntity,
}: {
  location: string;
  focusBus: string | null;
  focusEntity: string | null;
}) {
  const { scope, openLevel } = useLevelPage();
  const setColumnFilter = useLevelStore((s) => s.setColumnFilter);
  const look = useCarrierLook();
  const busesData = useBuses();
  const allBuses = busesData.status === "ready" ? busesData.data : NO_BUSES;
  const data = useSchematic(scope, location);
  const members = data.status === "ready" ? data.data : null;

  const busesHere = useMemo(() => {
    const order = busCarrierOrder(allBuses);
    return allBuses
      .filter((bus) => bus.location === location)
      .sort(
        (a, b) =>
          order.indexOf(a.carrier ?? "") - order.indexOf(b.carrier ?? "") ||
          Number(b.bus === location) - Number(a.bus === location) ||
          a.bus.localeCompare(b.bus),
      );
  }, [allBuses, location]);
  const busInfo = useMemo(() => new Map(allBuses.map((bus) => [bus.bus, bus])), [allBuses]);

  if (data.status === "error")
    return (
      <p className="text-danger-400 p-4 text-[11px]">Can't read this location: {data.error}</p>
    );
  if (!members || busesData.status !== "ready")
    return <p className="text-surface-500 p-4 text-[11px]">Loading the buses…</p>;
  if (busesHere.length === 0)
    return <p className="text-surface-500 p-4 text-[11px]">No buses at {location}.</p>;

  // Buses in a row.
  const n = busesHere.length;
  const spread = Math.min(260, 130 * (n - 1));
  const busAt = new Map(
    busesHere.map((bus, index) => [
      bus.bus,
      { x: n === 1 ? 330 : 330 - spread / 2 + (spread * index) / (n - 1), y: BUS_Y },
    ]),
  );
  const first = busesHere[0].bus;
  const last = busesHere[n - 1].bus;
  const here = (bus: string | null) => bus !== null && busAt.has(bus);

  const single = members.filter(
    (entity) => entity.ctype !== "Line" && entity.bus1 === null && here(entity.bus),
  );
  const singleGroups = groupBy(
    single,
    (entity) => `${entity.bus}|${entity.ctype}|${entity.carrier ?? ""}`,
  );
  const inner = members.filter(
    (entity) => entity.bus1 !== null && here(entity.bus) && here(entity.bus1),
  );
  const innerGroups = groupBy(
    inner,
    (entity) => `${entity.bus}|${entity.bus1}|${entity.ctype}|${entity.carrier ?? ""}`,
  );
  const outer = members.filter(
    (entity) => entity.bus1 !== null && here(entity.bus) !== here(entity.bus1),
  );

  const focusRow = focusEntity
    ? members.find((entity) => entity.entity === focusEntity)
    : undefined;
  const groupOn = (group: Group) =>
    focusEntity
      ? group.items.some((item) => item.entity === focusEntity)
      : focusBus
        ? group.items.some((item) => item.bus === focusBus || item.bus1 === focusBus)
        : true;
  const busOn = (bus: string) =>
    focusEntity ? focusRow?.bus === bus || focusRow?.bus1 === bus : !focusBus || focusBus === bus;
  const hasFocus = (group: Group) =>
    Boolean(focusEntity && group.items.some((item) => item.entity === focusEntity));

  const activate = (group: Group) => {
    if (group.items.length === 1) openLevel({ kind: "entity", entity: group.items[0].entity });
    else if (group.carrier !== null)
      setColumnFilter("carrier", { kind: "values", values: [group.carrier] });
  };
  const groupLabel = (group: Group) =>
    group.items.length === 1
      ? `${group.items[0].entity}: open it`
      : `${group.items.length} ${look.name(group.carrier)} ${group.ctype} entities: filter the table`;
  const countText = (group: Group) =>
    `${look.name(group.carrier)}${group.items.length > 1 ? ` ×${group.items.length}` : ""}`;

  const parts: ReactNode[] = [];

  // Single-bus groups: left of the first bus, right of the last, above the others.
  const columns = new Map<string, Group[]>();
  for (const group of singleGroups) {
    const side = group.bus === first ? "left" : group.bus === last ? "right" : `top:${group.bus}`;
    columns.set(side, [...(columns.get(side) ?? []), group]);
  }
  for (const [side, groups] of columns) {
    const step = Math.min(36, (H - 150) / Math.max(1, groups.length - 1));
    groups.forEach((group, index) => {
      const bus = busAt.get(group.bus)!;
      const color = look.color(group.carrier);
      const me = hasFocus(group);
      let p: { x: number; y: number };
      let path: string;
      let text: { x: number; y: number; anchor: "start" | "end" | "middle" };
      if (side === "left") {
        p = { x: 110, y: BUS_Y - (step * (groups.length - 1)) / 2 + index * step };
        path = `M${p.x + 9} ${p.y} C${p.x + 80} ${p.y} ${bus.x - 90} ${bus.y} ${bus.x - BUS_R - 2} ${bus.y}`;
        text = { x: p.x - 13, y: p.y + 4, anchor: "end" };
      } else if (side === "right") {
        p = { x: 600, y: BUS_Y - (step * (groups.length - 1)) / 2 + index * step };
        path = `M${p.x - 9} ${p.y} C${p.x - 60} ${p.y} ${bus.x + 70} ${bus.y} ${bus.x + BUS_R + 2} ${bus.y}`;
        text = { x: p.x + 13, y: p.y + 4, anchor: "start" };
      } else {
        const across = Math.min(60, 200 / Math.max(1, groups.length));
        p = { x: bus.x - (across * (groups.length - 1)) / 2 + index * across, y: 50 };
        path = `M${p.x} ${p.y + 9} L${bus.x} ${bus.y - BUS_R - 2}`;
        text = { x: p.x, y: p.y - 12, anchor: "middle" };
      }
      parts.push(
        <Hit
          key={`single-${group.key}`}
          label={groupLabel(group)}
          onActivate={() => activate(group)}
          opacity={groupOn(group) ? 1 : FADED}
        >
          <path
            d={path}
            fill="none"
            stroke={color}
            strokeWidth={me ? 3 : 1.5}
            markerEnd="url(#schematic-arrow)"
          />
          {me && <circle cx={p.x} cy={p.y} r={13} fill="none" stroke={FOCUS} strokeWidth={2} />}
          <EntityShape ctype={group.ctype} x={p.x} y={p.y} size={7} color={color} />
          <text
            x={text.x}
            y={text.y}
            textAnchor={text.anchor}
            fontSize={10.5}
            fill="var(--color-surface-200)"
          >
            {countText(group)}
          </text>
        </Hit>,
      );
    });
  }

  // Links between the buses: alternately above and below, further out each time.
  const perPair = new Map<string, number>();
  for (const group of innerGroups) {
    const pair = [group.bus, group.bus1].sort().join("|");
    const index = perPair.get(pair) ?? 0;
    perPair.set(pair, index + 1);
    const a = busAt.get(group.bus)!;
    const b = busAt.get(group.bus1!)!;
    const up = index % 2 === 0 ? -1 : 1;
    const bend = 58 + Math.floor(index / 2) * 34;
    const mx = (a.x + b.x) / 2;
    const my = BUS_Y + up * bend * 2;
    const color = look.color(group.carrier);
    const me = hasFocus(group);
    const labelY = BUS_Y + up * (bend + 14);
    parts.push(
      <Hit
        key={`inner-${group.key}`}
        label={groupLabel(group)}
        onActivate={() => activate(group)}
        opacity={groupOn(group) ? 1 : FADED}
      >
        <path
          d={`M${a.x} ${a.y + up * BUS_R} Q${mx} ${my} ${b.x} ${b.y + up * BUS_R}`}
          fill="none"
          stroke={color}
          strokeWidth={me ? 3.5 : 2}
          markerEnd="url(#schematic-arrow)"
        />
        <rect
          x={mx - 6}
          y={BUS_Y + up * bend - 6}
          width={12}
          height={12}
          transform={`rotate(45 ${mx} ${BUS_Y + up * bend})`}
          fill={color}
        />
        <text
          x={mx}
          y={labelY + (up < 0 ? -2 : 8)}
          textAnchor="middle"
          fontSize={10}
          fill="var(--color-surface-200)"
        >
          {countText(group)}
        </text>
      </Hit>,
    );
  }

  // Lines and links to other locations: along the bottom.
  outer.forEach((entity, index) => {
    const localBus = here(entity.bus) ? entity.bus! : entity.bus1!;
    const farBus = here(entity.bus) ? entity.bus1! : entity.bus!;
    const far = busInfo.get(farBus);
    const farLocation = far?.location ?? (here(entity.bus) ? entity.location1 : entity.location);
    const from = busAt.get(localBus)!;
    const x = outer.length > 1 ? 90 + (index * 480) / (outer.length - 1) : from.x;
    const me = entity.entity === focusEntity;
    const on = focusEntity ? me : focusBus ? focusBus === localBus : true;
    const mx = (from.x + x) / 2;
    const my = (from.y + BUS_R + BOTTOM_Y - 12) / 2;
    parts.push(
      <g key={`outer-${entity.entity}`}>
        <Hit
          label={`${entity.ctype} ${entity.entity}: open it`}
          onActivate={() => openLevel({ kind: "entity", entity: entity.entity })}
          opacity={on ? 1 : FADED}
        >
          <line
            x1={from.x}
            y1={from.y + BUS_R}
            x2={x}
            y2={BOTTOM_Y - 12}
            stroke="transparent"
            strokeWidth={12}
          />
          <line
            x1={from.x}
            y1={from.y + BUS_R}
            x2={x}
            y2={BOTTOM_Y - 12}
            stroke={me ? HALO : entity.ctype === "Line" ? LINE : look.color(entity.carrier)}
            strokeWidth={me ? 3.5 : 1.6}
            strokeDasharray={me ? undefined : "5 3"}
          />
          {outer.length <= 12 && (
            <text
              x={mx + 4}
              y={my}
              fontSize={9}
              fill="var(--color-surface-300)"
              stroke="var(--color-surface-950)"
              strokeWidth={3}
              paintOrder="stroke"
            >
              {shortId(entity.entity, 16)}
            </text>
          )}
        </Hit>
        <Hit
          label={`Bus ${farBus}${farLocation ? ` at ${farLocation}` : ""}: open its location`}
          onActivate={() =>
            farLocation
              ? openLevel({ kind: "location", location: farLocation })
              : openLevel({ kind: "bus", bus: farBus, location: null })
          }
          opacity={on ? 1 : 0.35}
        >
          <circle
            cx={x}
            cy={BOTTOM_Y}
            r={11}
            fill={look.color(far?.carrier ?? null)}
            fillOpacity={0.35}
            stroke={look.color(far?.carrier ?? null)}
            strokeWidth={1.5}
          />
          <text
            x={x}
            y={BOTTOM_Y + 24}
            textAnchor="middle"
            fontSize={9}
            fill="var(--color-surface-200)"
            className="font-mono"
          >
            {shortId(farLocation ?? farBus, 16)}
          </text>
        </Hit>
      </g>,
    );
  });

  // The buses, on top.
  for (const bus of busesHere) {
    const p = busAt.get(bus.bus)!;
    const color = look.color(bus.carrier);
    parts.push(
      <Hit
        key={`bus-${bus.bus}`}
        label={`Bus ${bus.bus}: open it`}
        onActivate={() => openLevel({ kind: "bus", bus: bus.bus, location })}
        opacity={busOn(bus.bus) ? 1 : 0.3}
      >
        {focusBus === bus.bus && (
          <circle cx={p.x} cy={p.y} r={BUS_R + 5} fill="none" stroke={FOCUS} strokeWidth={2} />
        )}
        <circle
          cx={p.x}
          cy={p.y}
          r={BUS_R}
          fill={color}
          fillOpacity={0.9}
          stroke="var(--color-surface-900)"
          strokeWidth={3}
        />
        <text
          x={p.x}
          y={p.y + 4}
          textAnchor="middle"
          fontSize={11.5}
          fontWeight={600}
          fill="#0a121d"
        >
          {shortId(look.name(bus.carrier), 9)}
        </text>
        <text
          x={p.x}
          y={p.y - BUS_R - 10}
          textAnchor="middle"
          fontSize={10}
          fill="var(--color-surface-300)"
          className="font-mono"
        >
          {shortId(bus.bus, 22)}
        </text>
      </Hit>,
    );
  }

  return (
    <div className="relative h-full w-full">
      <ZoomPanSvg
        width={W}
        height={H}
        resetKey={`schematic:${location}`}
        label={`Buses at ${location}`}
      >
        <defs>
          <marker
            id="schematic-arrow"
            viewBox="0 0 10 10"
            refX={9}
            refY={5}
            markerWidth={6}
            markerHeight={6}
            orient="auto-start-reverse"
          >
            <path d="M0 0 10 5 0 10z" fill="context-stroke" />
          </marker>
        </defs>
        {parts}
        {outer.length > 0 && (
          <text x={W - 12} y={H - 6} textAnchor="end" fontSize={10} fill="var(--color-surface-400)">
            Buses at other locations along the bottom
          </text>
        )}
      </ZoomPanSvg>
      <div className="bg-surface-900/80 text-surface-300 pointer-events-none absolute bottom-2 left-2 rounded px-1.5 py-1 text-[10px]">
        Click a bus, a line or a neighbouring bus to open it. A group (×n) filters the table.
      </div>
    </div>
  );
}
