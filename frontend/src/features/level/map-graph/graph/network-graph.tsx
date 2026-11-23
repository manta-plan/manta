import { useMemo } from "react";
import { useLevelPage } from "../../level-page-context";
import { useBranches, useBuses, type BusRow } from "../map-graph-data";
import { busCarrierOrder, useInnerLinks } from "./graph-data";
import { useCarrierLook } from "./graph-look";
import { Hit, LINE, MUTED } from "./graph-parts";
import { ZoomPanSvg } from "./zoom-pan-svg";

// All locations: every location's first-carrier bus at its coordinates,
// its other buses (H2, …) beside it joined by a short line in the colour of
// the link between them, and the lines between locations as dashed edges,
// wider by s_nom. A click opens a bus or a line.

const W = 660;
const H = 420;
const MARGIN = 28;
const NO_BUSES: BusRow[] = [];

export function NetworkGraph() {
  const { scope, openLevel } = useLevelPage();
  const look = useCarrierLook();
  const busesData = useBuses();
  const branchesData = useBranches(scope);
  const linksData = useInnerLinks(scope);
  const buses = busesData.status === "ready" ? busesData.data : NO_BUSES;
  const lines =
    branchesData.status === "ready"
      ? branchesData.data.filter((branch) => branch.ctype === "Line")
      : [];
  const innerLinks = linksData.status === "ready" ? linksData.data : [];

  const layout = useMemo(() => {
    const order = busCarrierOrder(buses);
    const rank = (carrier: string | null) => order.indexOf(carrier ?? "");
    // Equirectangular, shrunk by the cosine of the mean latitude, fitted to the box.
    const lat = buses.reduce((sum, bus) => sum + bus.y, 0) / Math.max(1, buses.length);
    const k = Math.cos((lat * Math.PI) / 180);
    const xs = buses.map((bus) => bus.x * k);
    const ys = buses.map((bus) => -bus.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const scale = Math.min(
      (W - 2 * MARGIN) / Math.max(1e-6, x1 - x0),
      (H - 2 * MARGIN) / Math.max(1e-6, y1 - y0),
    );
    const ox = (W - (x1 - x0) * scale) / 2;
    const oy = (H - (y1 - y0) * scale) / 2;
    const project = (lon: number, latitude: number) =>
      [ox + (lon * k - x0) * scale, oy + (-latitude - y0) * scale] as const;

    const byLocation = new Map<string, typeof buses>();
    for (const bus of buses)
      byLocation.set(bus.location, [...(byLocation.get(bus.location) ?? []), bus]);
    const places = new Map<string, { x: number; y: number }>();
    const nodes: {
      bus: string;
      location: string;
      carrier: string | null;
      x: number;
      y: number;
      main: boolean;
    }[] = [];
    for (const [location, here] of byLocation) {
      const sorted = [...here].sort(
        (a, b) =>
          Number(b.bus === location) - Number(a.bus === location) ||
          rank(a.carrier) - rank(b.carrier) ||
          a.bus.localeCompare(b.bus),
      );
      const [main, ...others] = sorted;
      const [x, y] = project(main.x, main.y);
      places.set(location, { x, y });
      nodes.push({ bus: main.bus, location, carrier: main.carrier, x, y, main: true });
      others.forEach((bus, index) => {
        // Beside the main bus, down and right first, then around it.
        const angle = Math.PI / 4 + (index * Math.PI) / 2.5;
        nodes.push({
          bus: bus.bus,
          location,
          carrier: bus.carrier,
          x: x + 12 * Math.cos(angle),
          y: y + 12 * Math.sin(angle),
          main: false,
        });
      });
    }
    return { nodes, places, byBus: new Map(nodes.map((node) => [node.bus, node])) };
  }, [buses]);

  if (busesData.status === "loading")
    return <p className="text-surface-500 p-4 text-[11px]">Loading the buses…</p>;
  if (busesData.status === "error")
    return (
      <p className="text-danger-400 p-4 text-[11px]">Can't read the buses: {busesData.error}</p>
    );

  const linkColor = new Map(
    innerLinks.map((link) => [`${link.bus0}|${link.bus1}`, look.color(link.carrier)]),
  );
  const maxCapacity = Math.max(1, ...lines.map((line) => line.capacity_opt ?? line.capacity ?? 0));
  const firstCarriers = [
    ...new Set(layout.nodes.filter((node) => node.main).map((node) => node.carrier)),
  ];
  const otherCarriers = [
    ...new Set(layout.nodes.filter((node) => !node.main).map((node) => node.carrier)),
  ];

  return (
    <div className="relative h-full w-full">
      <ZoomPanSvg
        width={W}
        height={H}
        resetKey="all-locations"
        label="All buses, placed by location"
      >
        {lines.map((line) => {
          const a = layout.places.get(line.location0);
          const b = layout.places.get(line.location1);
          if (!a || !b) return null;
          const width = 0.6 + (3.4 * (line.capacity_opt ?? line.capacity ?? 0)) / maxCapacity;
          return (
            <Hit
              key={line.entity}
              label={`Line ${line.entity}: ${line.location0} – ${line.location1}`}
              onActivate={() => openLevel({ kind: "entity", entity: line.entity })}
            >
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={8} />
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={LINE}
                strokeWidth={width}
                strokeDasharray="4 2"
              />
            </Hit>
          );
        })}
        {layout.nodes
          .filter((node) => !node.main)
          .map((node) => {
            const main = layout.places.get(node.location)!;
            const mainBus = layout.nodes.find(
              (other) => other.main && other.location === node.location,
            )!.bus;
            const color =
              linkColor.get(`${mainBus}|${node.bus}`) ??
              linkColor.get(`${node.bus}|${mainBus}`) ??
              MUTED;
            return (
              <line
                key={`join-${node.bus}`}
                x1={main.x}
                y1={main.y}
                x2={node.x}
                y2={node.y}
                stroke={color}
                strokeWidth={1.4}
              />
            );
          })}
        {layout.nodes.map((node) => (
          <Hit
            key={node.bus}
            label={`Bus ${node.bus} (${look.name(node.carrier)}): open it`}
            onActivate={() => openLevel({ kind: "bus", bus: node.bus, location: node.location })}
          >
            <circle
              cx={node.x}
              cy={node.y}
              r={node.main ? 5.5 : 3.5}
              fill={look.color(node.carrier)}
              stroke="var(--color-surface-900)"
              strokeWidth={node.main ? 1.5 : 1}
            />
          </Hit>
        ))}
      </ZoomPanSvg>
      <div className="bg-surface-900/80 text-surface-300 pointer-events-none absolute bottom-2 left-2 flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded px-1.5 py-1 text-[10px]">
        {[
          ...firstCarriers,
          ...otherCarriers.filter((carrier) => !firstCarriers.includes(carrier)),
        ].map((carrier) => (
          <span key={carrier ?? ""} className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: look.color(carrier) }}
            />
            {look.name(carrier)} bus
          </span>
        ))}
        <span>
          · dashed edges are lines, placed at bus coordinates · click a bus or a line to open it
        </span>
      </div>
    </div>
  );
}
