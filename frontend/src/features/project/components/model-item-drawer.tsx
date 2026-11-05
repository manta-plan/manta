import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "wouter";
import clsx from "clsx";
import { LuChartLine, LuCheck, LuCircleDot, LuLocateFixed, LuMapPin, LuX } from "react-icons/lu";
import { getActiveProjectTab } from "../lib/project-route";
import { useCopyToClipboard } from "../lib/use-copy-to-clipboard";
import {
  entityLabel,
  formatRatio,
  formatTimestamp,
  formatValue,
  isWkt,
} from "../lib/record-format";
import { changeKey, getEntity, getLabelDetail } from "../lib/record-server/queries";
import type {
  EntityAttribute,
  EntityConnection,
  ScenarioChangeValue,
} from "../lib/record-server/types";
import { parentLabel } from "../lib/record-scenarios";
import { useProjectStore } from "../store/project-store";
import type { RecordItem } from "../store/types";
import { CopyWktButton } from "./copy-wkt-button";

interface ItemDetail {
  title: string;
  subtitle: string;
  properties: [string, string, string | null][];
  connections: EntityConnection[];
  attributes: EntityAttribute[];
  // What the attributes are about, as scenario changes name it.
  subject: { dim: string; label: string };
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-surface-500 text-[10px] font-semibold tracking-wide uppercase">
        {title}
        {count !== undefined && <span className="ml-1 font-normal tabular-nums">{count}</span>}
      </h3>
      {children}
    </section>
  );
}

function Row({
  label,
  title,
  muted,
  children,
}: {
  label: string;
  title?: string;
  muted?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-baseline gap-2 text-[12px]"
      title={title}
    >
      <span className="text-surface-400 truncate">{label}</span>
      <span className={clsx("min-w-0 break-words", muted ? "text-surface-500" : "text-surface-50")}>
        {children}
      </span>
    </div>
  );
}

// What the shown scenario changed in a value, against the one it starts from.
function ChangeNote({
  change,
  spec,
  from,
}: {
  change: ScenarioChangeValue;
  spec: EntityAttribute["spec"];
  from: string;
}) {
  const text =
    change.seriesRows > 0
      ? `${change.seriesRows.toLocaleString()} changed ${formatRatio(change.ratio)}`
      : change.before === null
        ? `not in ${from}`
        : `was ${formatValue(change.before, spec)}`;
  return (
    <span
      className="text-surface-400 block truncate text-[11px]"
      title={`Changed by this scenario; ${from} has ${change.seriesRows > 0 ? "other values" : formatValue(change.before, spec)}`}
    >
      {text}
    </span>
  );
}

function AttributeRow({
  attribute,
  entity,
  change,
  from,
}: {
  attribute: EntityAttribute;
  entity: string | null;
  change?: ScenarioChangeValue;
  from: string;
}) {
  const openSeriesChart = useProjectStore((s) => s.openSeriesChart);
  const { name, spec, bus, value, isDefault, seriesRows } = attribute;
  const label = bus ? `${name} → ${bus}` : name;
  const title = `${spec.description}${spec.unit ? ` (${spec.unit})` : ""}${isDefault ? "\nNot stored: the manifest default." : ""}`;
  return (
    <Row label={label} title={title} muted={isDefault}>
      <span className={clsx("flex items-baseline gap-1.5", change && "text-accent-300")}>
        {seriesRows > 0 && entity ? (
          <button
            type="button"
            onClick={() => openSeriesChart(entity, name, bus)}
            className="text-accent-400 hover:text-accent-300 flex items-center gap-1 outline-none"
            title="Varies by snapshot: open the chart"
          >
            <LuChartLine size={12} />
            {seriesRows.toLocaleString()} points
          </button>
        ) : (
          <span className="min-w-0">{formatValue(value, spec)}</span>
        )}
        {isDefault && (
          <span className="text-surface-500 shrink-0 text-[10px] tracking-wide uppercase">
            default
          </span>
        )}
        {value && isWkt(value) && <CopyWktButton wkt={value} />}
      </span>
      {change && <ChangeNote change={change} spec={spec} from={from} />}
    </Row>
  );
}

function useItemDetail(item: RecordItem | null): {
  detail: ItemDetail | null;
  error: string | null;
} {
  const record = useProjectStore((s) => s.record);
  const [state, setState] = useState<{
    key: string;
    detail: ItemDetail | null;
    error: string | null;
  } | null>(null);
  const key = item ? JSON.stringify(item) : "";

  useEffect(() => {
    if (!item || !record) return;
    let cancelled = false;
    const load = async (): Promise<ItemDetail> => {
      if (item.kind === "entity") {
        const entity = await getEntity(item.entity, record.info.manifest);
        if (!entity) throw new Error("This entity is not in the record.");
        const carrier = entity.properties.carrier ? String(entity.properties.carrier) : null;
        return {
          title: entityLabel(item.entity, item.locations[0] ?? null),
          subtitle: item.entity,
          properties: Object.entries(entity.properties)
            .filter(([key]) => key !== "entity")
            .map(([key, value]) => [
              key,
              key === "carrier" && carrier
                ? (record.carriers[carrier]?.niceName ?? carrier)
                : formatValue(value === null ? null : String(value)),
              key === "carrier" ? (record.carriers[carrier ?? ""]?.color ?? null) : null,
            ]),
          connections: entity.connections,
          attributes: entity.attributes,
          subject: { dim: "entity", label: item.entity },
        };
      }
      const label = await getLabelDetail(item.dim, item.label, record.info);
      return {
        title: item.name ?? item.label,
        subtitle: item.dim,
        properties: Object.entries(label.properties).map(([key, value]) => [
          key,
          key === "timestep"
            ? formatTimestamp(value)
            : formatValue(value === null ? null : String(value)),
          key === "carrier"
            ? (record.carriers[String(value)]?.color ?? null)
            : key === "color"
              ? String(value)
              : null,
        ]),
        connections: [],
        attributes: label.attributes,
        // A connection's values are its entity's, per bus.
        subject:
          item.dim === "connection"
            ? { dim: "entity", label: String(label.properties.entity) }
            : { dim: item.dim, label: item.label },
      };
    };
    load()
      .then((detail) => !cancelled && setState({ key, detail, error: null }))
      .catch(
        (error: unknown) =>
          !cancelled &&
          setState({
            key,
            detail: null,
            error: error instanceof Error ? error.message : String(error),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [item, key, record]);

  return state?.key === key ? state : { detail: null, error: null };
}

// Left-side counterpart to RightDrawer's layer 2 — stacks just inside the
// main Sidebar (rendered at left-0 of <main>, which starts right where the
// sidebar ends) rather than covering it. Shows what the record holds for the
// item picked in the tree.
export function ModelItemDrawer() {
  const item = useProjectStore((s) => s.itemDrawer);
  const closeItemDrawer = useProjectStore((s) => s.closeItemDrawer);
  const focusMap = useProjectStore((s) => s.focusMap);
  const openLocationView = useProjectStore((s) => s.openLocationView);
  const { detail, error } = useItemDetail(item);
  const { copied, copy } = useCopyToClipboard();

  const [location] = useLocation();
  const activeTab = getActiveProjectTab(location);
  useEffect(() => {
    if (activeTab !== "model") closeItemDrawer();
  }, [activeTab, closeItemDrawer]);

  const stored = detail?.attributes.filter((attribute) => !attribute.isDefault) ?? [];
  const defaults = detail?.attributes.filter((attribute) => attribute.isDefault) ?? [];
  const entity = item?.kind === "entity" ? item.entity : null;
  const record = useProjectStore((s) => s.record);
  const from = record ? parentLabel(record.info, record.scenario) : "";
  // Where the entity is: its real locations (a line or link has two), and
  // their points on the map. A virtual location (EU) has no point.
  const locations = item?.kind === "entity" ? [...new Set(item.locations)] : [];
  const points = locations.flatMap((name): [number, number][] => {
    const location = record?.locations.find((candidate) => candidate.location === name);
    return location ? [[location.x, location.y]] : [];
  });
  const locationTitle =
    locations.length === 1 ? `Location ${locations[0]}` : `Locations ${locations.join(" and ")}`;
  const changeOf = (attribute: EntityAttribute) =>
    detail
      ? record?.changes.get(
          changeKey(attribute.name, detail.subject.dim, detail.subject.label, attribute.bus),
        )
      : undefined;

  return (
    <aside
      className={clsx(
        "absolute top-0 left-0 z-20 flex h-full w-72 flex-col border-r border-surface-600/60 bg-surface-800/70 backdrop-blur-xl transition-transform duration-200 ease-out",
        item ? "translate-x-0 pointer-events-auto" : "-translate-x-full pointer-events-none",
      )}
    >
      <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between gap-2 border-b px-3">
        <div className="text-surface-200 flex min-w-0 items-center gap-1.5 text-[11px] font-semibold tracking-wide">
          {copied ? (
            <LuCheck size={12} className="text-accent-400 shrink-0" />
          ) : (
            <LuCircleDot size={12} className="shrink-0" />
          )}
          {/* Ids are long: truncate, keep the full id in the tooltip, copy it on click. */}
          <button
            type="button"
            onClick={() => detail && copy(item?.kind === "label" ? detail.title : detail.subtitle)}
            title={copied ? "Copied" : `${detail?.subtitle ?? ""}\nClick to copy the id`}
            className="hover:text-surface-50 min-w-0 truncate outline-none"
          >
            {detail?.title ?? "Loading…"}
          </button>
        </div>
        <button
          onClick={closeItemDrawer}
          aria-label="Close"
          className="text-surface-400 hover:text-surface-100 shrink-0 outline-none"
        >
          <LuX size={14} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
        {error && <div className="text-danger-500 text-[12px]">{error}</div>}
        {!detail && !error && <div className="text-surface-400 text-[12px]">Loading…</div>}
        {detail && (
          <>
            {detail.properties.length > 0 && (
              <Section title="Properties">
                {detail.properties.map(([key, value, color]) => (
                  <Row key={key} label={key}>
                    <span className="flex items-center gap-1.5">
                      {color && (
                        <span
                          className="h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: color }}
                        />
                      )}
                      {value}
                    </span>
                  </Row>
                ))}
              </Section>
            )}
            {detail.connections.length > 0 && (
              <Section title="Connections" count={detail.connections.length}>
                {detail.connections.map((connection) => (
                  <Row
                    key={`${connection.role}:${connection.bus}`}
                    label={connection.role}
                    title={`${connection.bus}\nat ${connection.location}`}
                  >
                    <span className="block truncate">{connection.bus}</span>
                    <span className="text-surface-400 block truncate text-[11px]">
                      {connection.busCarrier} bus
                    </span>
                  </Row>
                ))}
              </Section>
            )}
            <Section title="Attributes" count={stored.length}>
              {stored.length === 0 ? (
                <div className="text-surface-500 text-[12px]">Nothing stored.</div>
              ) : (
                stored.map((attribute) => (
                  <AttributeRow
                    key={`${attribute.name}:${attribute.bus ?? ""}`}
                    attribute={attribute}
                    entity={entity}
                    change={changeOf(attribute)}
                    from={from}
                  />
                ))
              )}
            </Section>
            {defaults.length > 0 && (
              <Section title="Defaults" count={defaults.length}>
                {defaults.map((attribute) => (
                  <AttributeRow
                    key={attribute.name}
                    attribute={attribute}
                    entity={entity}
                    from={from}
                  />
                ))}
              </Section>
            )}
          </>
        )}
      </div>

      {points.length > 0 && (
        <div className="border-surface-600/60 flex shrink-0 gap-2 border-t p-3">
          <button
            type="button"
            onClick={() => focusMap(points)}
            className="border-surface-600 text-surface-200 hover:bg-surface-700 flex flex-1 items-center justify-center gap-1.5 rounded border px-3 py-1.5 text-[12px] font-medium outline-none"
          >
            <LuLocateFixed size={13} className="shrink-0" />
            Show on map
          </button>
          <button
            type="button"
            onClick={() => openLocationView(locationTitle, locations)}
            title={`Everything at ${locations.join(" and ")}`}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-100 flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-[12px] outline-none"
          >
            <LuMapPin size={13} className="shrink-0" />
            <span className="truncate">Everything at {locations.join(" & ")}</span>
          </button>
        </div>
      )}
    </aside>
  );
}
