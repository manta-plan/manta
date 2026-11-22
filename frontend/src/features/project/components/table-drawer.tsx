import { useEffect, useMemo, useState } from "react";
import { Drawer } from "@base-ui/react/drawer";
import type { EChartsOption } from "echarts";
import clsx from "clsx";
import {
  LuChartLine,
  LuDownload,
  LuGitCompareArrows,
  LuMapPin,
  LuSearch,
  LuTable,
  LuX,
} from "react-icons/lu";
import { useAppStore } from "../../home/store";
import { useProjectStore } from "../store/project-store";
import type { TableDrawerContent } from "../store/types";
import { entityLabel, formatNumber, formatRatio, formatValue } from "../lib/record-format";
import {
  changeKey,
  getEntities,
  getEntityValues,
  getScenarioChange,
  getSeries,
} from "../lib/record-server/queries";
import type {
  AttributeSpec,
  EntityListItem,
  EntityValue,
  ScenarioChange,
  ScenarioChangeValue,
  SeriesPoint,
} from "../lib/record-server/types";
import { parentLabel } from "../lib/record-scenarios";
import { EChart } from "./echart";
import { LocationView } from "./location-view";

const SNAP_POINTS = ["160px", 0.5, 0.92];

const DUMMY_ROWS = Array.from({ length: 60 }, (_, i) => ({
  id: i,
  name: `row_${i + 1}`,
  value: (Math.random() * 1000).toFixed(2),
  unit: i % 2 === 0 ? "MW" : "MWh",
}));

function Message({ children }: { children: string }) {
  return (
    <div className="text-surface-400 flex h-full items-center justify-center text-[12px]">
      {children}
    </div>
  );
}

// Fetches once per key; the previous result shows nothing while a new key loads.
function useFetched<T>(
  key: string,
  fetcher: () => Promise<T>,
): { data: T | null; error: string | null } {
  const [state, setState] = useState<{ key: string; data: T | null; error: string | null } | null>(
    null,
  );
  useEffect(() => {
    let cancelled = false;
    fetcher()
      .then((data) => !cancelled && setState({ key, data, error: null }))
      .catch(
        (error: unknown) =>
          !cancelled &&
          setState({
            key,
            data: null,
            error: error instanceof Error ? error.message : String(error),
          }),
      );
    return () => {
      cancelled = true;
    };
    // The key names what's fetched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state?.key === key ? state : { data: null, error: null };
}

// A changed cell's tooltip: what the scenario's parent has there.
function changeTitle(
  changes: ScenarioChangeValue[],
  from: string,
  spec: AttributeSpec | undefined,
): string {
  const was = changes.map((change) =>
    change.seriesRows > 0
      ? `${change.seriesRows.toLocaleString()} rows changed ${formatRatio(change.ratio)}`
      : formatValue(change.before, spec),
  );
  return `Changed by this scenario; ${from} has ${was.join(" / ")}`;
}

// One row per entity, one column per attribute any of them stores.
function EntityTable({ ctype, carrier }: { ctype: string; carrier: string | null }) {
  const record = useProjectStore((s) => s.record);
  const openItemDrawer = useProjectStore((s) => s.openItemDrawer);
  const openSeriesChart = useProjectStore((s) => s.openSeriesChart);
  const [search, setSearch] = useState("");
  const from = record ? parentLabel(record.info, record.scenario) : "";
  const { data, error } = useFetched<[EntityListItem[], EntityValue[]]>(
    `${record?.scenario}\n${ctype}\n${carrier}`,
    () => Promise.all([getEntities(ctype, carrier), getEntityValues(ctype, carrier)]),
  );

  const table = useMemo(() => {
    if (!data) return null;
    const [entities, values] = data;
    const byEntity = new Map<string, Map<string, EntityValue[]>>();
    const counts = new Map<string, number>();
    for (const value of values) {
      const cells = byEntity.get(value.entity) ?? new Map<string, EntityValue[]>();
      cells.set(value.attribute, [...(cells.get(value.attribute) ?? []), value]);
      byEntity.set(value.entity, cells);
      counts.set(value.attribute, (counts.get(value.attribute) ?? 0) + 1);
    }
    // Most-stored attributes first.
    const columns = [...counts]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([attribute]) => attribute);
    return { entities, byEntity, columns };
  }, [data]);

  if (error) return <Message>{error}</Message>;
  if (!table || !record) return <Message>Loading…</Message>;
  const query = search.trim().toLowerCase();
  const rows = query
    ? table.entities.filter((item) => item.entity.toLowerCase().includes(query))
    : table.entities;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-surface-700 bg-surface-800 flex min-h-10 shrink-0 items-center gap-2 border-b px-3 py-1.5">
        <label className="border-surface-600 bg-surface-900/70 text-surface-400 focus-within:border-surface-500 focus-within:text-surface-200 flex h-7 max-w-[340px] min-w-[180px] flex-1 items-center gap-1.5 rounded border px-2">
          <LuSearch size={13} className="shrink-0" />
          <input
            aria-label="Search entities"
            placeholder="Search entities"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="text-surface-200 placeholder:text-surface-500 min-w-0 flex-1 bg-transparent text-[12px] outline-none"
          />
        </label>
        <span className="text-surface-400 text-[11px]">
          {rows.length.toLocaleString()} of {table.entities.length.toLocaleString()} · values not
          shown are defaults
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <thead className="bg-surface-800 text-surface-400 sticky top-0 z-10 text-left">
            <tr>
              <th className="border-surface-600 bg-surface-800 sticky left-0 border-b px-3 py-1.5 font-medium">
                Entity
              </th>
              {table.columns.map((column) => {
                const spec = record.info.manifest.attributes[column];
                return (
                  <th
                    key={column}
                    title={spec?.description}
                    className="border-surface-600 border-b px-3 py-1.5 font-medium whitespace-nowrap"
                  >
                    {column}
                    {spec?.unit && (
                      <span className="text-surface-500 ml-1 font-normal">{spec.unit}</span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => {
              const cells = table.byEntity.get(item.entity);
              return (
                <tr key={item.entity} className="text-surface-200 hover:bg-surface-700/60">
                  <td
                    className="border-surface-700/60 bg-surface-800 sticky left-0 max-w-[280px] truncate border-b px-3 py-1 font-mono"
                    title={item.entity}
                  >
                    <button
                      type="button"
                      onClick={() =>
                        openItemDrawer({
                          kind: "entity",
                          entity: item.entity,
                          ctype,
                          carrier,
                          locations: [item.location, ...item.outputs].filter(
                            (location): location is string => Boolean(location),
                          ),
                        })
                      }
                      className="hover:text-accent-300 max-w-full truncate text-left outline-none"
                    >
                      {entityLabel(item.entity, item.location)}
                    </button>
                  </td>
                  {table.columns.map((column) => {
                    const values = cells?.get(column) ?? [];
                    const series = values.find((value) => value.seriesRows > 0);
                    const changes = values
                      .map((value) =>
                        record.changes.get(changeKey(column, "entity", item.entity, value.bus)),
                      )
                      .filter((change) => change !== undefined);
                    return (
                      <td
                        key={column}
                        title={
                          changes.length > 0
                            ? changeTitle(changes, from, record.info.manifest.attributes[column])
                            : undefined
                        }
                        className={clsx(
                          "border-b border-surface-700/60 px-3 py-1 whitespace-nowrap",
                          changes.length > 0
                            ? "bg-accent-600/15 text-accent-200"
                            : "text-surface-400",
                        )}
                      >
                        {series ? (
                          <button
                            type="button"
                            onClick={() => openSeriesChart(item.entity, column, series.bus)}
                            className="text-accent-400 hover:text-accent-300 flex items-center gap-1 outline-none"
                          >
                            <LuChartLine size={11} />
                            {series.seriesRows}
                          </button>
                        ) : values.length > 0 ? (
                          values
                            .map((value) =>
                              formatValue(value.constant, {
                                dtype: record.info.manifest.attributes[column]?.dtype,
                                unit: null,
                              }),
                            )
                            .join(" / ")
                        ) : (
                          ""
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// One attribute a scenario changes: per entity or bus, its value in the
// parent revision and in the scenario. A series shows how many of its rows
// changed and their median ratio instead.
function ScenarioChangeTable({ scenario, attribute }: { scenario: string; attribute: string }) {
  const record = useProjectStore((s) => s.record);
  const openItemDrawer = useProjectStore((s) => s.openItemDrawer);
  const { data, error } = useFetched<ScenarioChange[]>(`${scenario}\n${attribute}`, () =>
    getScenarioChange(scenario, attribute),
  );

  if (error) return <Message>{error}</Message>;
  if (!data || !record) return <Message>Loading…</Message>;
  const revisions = record.info.revisions;
  const revision = revisions.find((r) => r.name === scenario);
  const parent = revisions.find((r) => r.name === revision?.parent);
  const spec = record.info.manifest.attributes[attribute];
  const isSeries = data.some((row) => row.seriesRows > 0);
  const isBus = data[0]?.dim === "bus";
  const show = (value: string | null) => formatValue(value, { dtype: spec?.dtype, unit: null });
  const cell = "border-b border-surface-700/60 px-3 py-1 whitespace-nowrap";
  const head = "border-b border-surface-600 px-3 py-1.5 font-medium whitespace-nowrap";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-surface-700 bg-surface-800 text-surface-400 flex min-h-10 shrink-0 items-center gap-2 border-b px-3 py-1.5 text-[11px]">
        <span title={spec?.description}>
          {data.length.toLocaleString()}{" "}
          {isBus
            ? data.length === 1
              ? "bus"
              : "buses"
            : data.length === 1
              ? "entity"
              : "entities"}
          {spec?.unit && ` · ${spec.unit}`} · before is {parent?.label ?? "the parent"}, after is{" "}
          {revision?.label ?? scenario}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <thead className="bg-surface-800 text-surface-400 sticky top-0 z-10 text-left">
            <tr>
              <th className={`bg-surface-800 sticky left-0 ${head}`}>{isBus ? "Bus" : "Entity"}</th>
              <th className={head}>Location</th>
              {!isBus && <th className={head}>Carrier</th>}
              {isSeries ? (
                <th className={head}>Changed rows</th>
              ) : (
                <>
                  <th className={head}>Before</th>
                  <th className={head}>After</th>
                </>
              )}
              <th className={head}>{isSeries ? "Median ratio" : "Ratio"}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => {
              const carrier = row.carrier ? record.carriers[row.carrier] : undefined;
              const name = row.bus ? `${row.label} → ${row.bus}` : row.label;
              return (
                <tr
                  key={`${row.label}\n${row.bus}`}
                  className="text-surface-200 hover:bg-surface-700/60"
                >
                  <td
                    className={`bg-surface-800 sticky left-0 max-w-[320px] truncate font-mono ${cell}`}
                    title={name}
                  >
                    <button
                      type="button"
                      onClick={() =>
                        isBus
                          ? openItemDrawer({ kind: "label", dim: "bus", label: row.label })
                          : row.ctype &&
                            openItemDrawer({
                              kind: "entity",
                              entity: row.label,
                              ctype: row.ctype,
                              carrier: row.carrier,
                              locations: row.location ? [row.location] : [],
                            })
                      }
                      className="hover:text-accent-300 max-w-full truncate text-left outline-none"
                    >
                      {isBus ? row.label : entityLabel(row.label, row.location)}
                      {row.bus && <span className="text-surface-500"> → {row.bus}</span>}
                    </button>
                  </td>
                  <td className={`text-surface-400 ${cell}`}>{row.location ?? "—"}</td>
                  {!isBus && (
                    <td className={`text-surface-400 ${cell}`}>
                      <span className="flex items-center gap-1.5">
                        {carrier?.color && (
                          <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ backgroundColor: carrier.color }}
                          />
                        )}
                        {carrier?.niceName || row.carrier || "—"}
                      </span>
                    </td>
                  )}
                  {isSeries ? (
                    <td className={`text-surface-300 tabular-nums ${cell}`}>
                      {formatNumber(row.seriesRows)}
                    </td>
                  ) : (
                    <>
                      <td className={`text-surface-400 tabular-nums ${cell}`}>
                        {show(row.before)}
                      </td>
                      <td className={`text-surface-100 tabular-nums ${cell}`}>{show(row.after)}</td>
                    </>
                  )}
                  <td className={`text-accent-300 tabular-nums ${cell}`}>
                    {formatRatio(row.ratio)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// An attribute's values over snapshots: one line per period across its
// timesteps, since every period repeats the same timesteps.
function SeriesChart({
  entity,
  attribute,
  bus,
}: {
  entity: string;
  attribute: string;
  bus: string | null;
}) {
  const record = useProjectStore((s) => s.record);
  const theme = useAppStore((s) => s.theme);
  const spec = record?.info.manifest.attributes[attribute];
  const { data, error } = useFetched<SeriesPoint[]>(
    `${record?.scenario}\n${entity}\n${attribute}\n${bus}`,
    () =>
      spec
        ? getSeries(attribute, spec, entity, bus)
        : Promise.reject(new Error(`${attribute} is not in the manifest.`)),
  );

  const option = useMemo<EChartsOption | null>(() => {
    if (!data || data.length === 0) return null;
    const dark = theme === "dark";
    const timesteps = [...new Set(data.map((point) => point.timestep ?? String(point.snapshot)))];
    const periods = [...new Set(data.map((point) => point.period ?? 0))].sort();
    const axisColor = dark ? "#a0b6ca" : "#475569";
    const zoomable = timesteps.length > 48;
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", valueFormatter: (value) => Number(value).toLocaleString() },
      legend: periods.length > 1 ? { top: 0, textStyle: { color: axisColor } } : undefined,
      grid: { left: 64, right: 24, top: periods.length > 1 ? 32 : 16, bottom: zoomable ? 50 : 32 },
      xAxis: {
        type: "category",
        data: timesteps,
        axisLabel: { color: axisColor, fontSize: 11 },
        axisLine: { lineStyle: { color: dark ? "#2c4763" : "#cbd5e1" } },
      },
      yAxis: {
        type: "value",
        name: spec?.unit ?? undefined,
        nameTextStyle: { color: axisColor },
        axisLabel: { color: axisColor, fontSize: 11 },
        splitLine: { lineStyle: { color: dark ? "#16253a" : "#e2e8f0" } },
      },
      dataZoom: zoomable
        ? [{ type: "inside" }, { type: "slider", height: 14, bottom: 8 }]
        : undefined,
      series: periods.map((period) => ({
        name: String(period),
        type: "line",
        showSymbol: true,
        data: timesteps.map(
          (timestep) =>
            data.find(
              (point) =>
                (point.period ?? 0) === period &&
                (point.timestep ?? String(point.snapshot)) === timestep,
            )?.value ?? null,
        ),
      })),
    };
  }, [data, spec?.unit, theme]);

  if (error) return <Message>{error}</Message>;
  if (!data) return <Message>Loading…</Message>;
  if (!option) return <Message>No snapshot values stored.</Message>;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <div className="text-surface-300 flex flex-wrap items-center justify-between gap-2 text-[12px]">
        <span title={spec?.description}>
          <span className="text-surface-50 font-medium">{attribute}</span>
          {bus && <span className="text-surface-400"> → {bus}</span>} · {entity}
        </span>
        <button
          type="button"
          title="Download CSV"
          aria-label="Download CSV"
          onClick={() => {
            const csv = [
              "snapshot,period,timestep,value",
              ...data.map(
                (point) =>
                  `${point.snapshot},${point.period ?? ""},${point.timestep ?? ""},${point.value ?? ""}`,
              ),
            ].join("\n");
            const href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
            const link = document.createElement("a");
            link.href = href;
            link.download = `${attribute}.csv`;
            link.click();
            URL.revokeObjectURL(href);
          }}
          className="border-surface-600 text-surface-300 hover:bg-surface-700 hover:text-surface-100 grid h-8 w-8 place-items-center rounded border outline-none"
        >
          <LuDownload size={13} />
        </button>
      </div>
      <EChart option={option} className="h-80 w-full shrink-0" />
    </div>
  );
}

function DummyTable() {
  return (
    <table className="w-full border-collapse">
      <thead className="bg-surface-800 text-surface-400 sticky top-0 text-left">
        <tr>
          <th className="border-surface-600 border-b px-3 py-1.5 font-medium">Name</th>
          <th className="border-surface-600 border-b px-3 py-1.5 font-medium">Value</th>
          <th className="border-surface-600 border-b px-3 py-1.5 font-medium">Unit</th>
        </tr>
      </thead>
      <tbody>
        {DUMMY_ROWS.map((row) => (
          <tr key={row.id} className="text-surface-200 hover:bg-surface-700/60">
            <td className="border-surface-700/60 border-b px-3 py-1 font-mono">{row.name}</td>
            <td className="border-surface-700/60 border-b px-3 py-1 font-mono">{row.value}</td>
            <td className="border-surface-700/60 text-surface-400 border-b px-3 py-1">
              {row.unit}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function drawerTitle(
  content: TableDrawerContent,
  carrierName: (carrier: string) => string,
  scenarioLabel: (name: string) => string,
): string {
  switch (content.kind) {
    case "catalog":
      return content.title;
    case "entities":
      return `${content.ctype}${content.carrier ? ` · ${carrierName(content.carrier)}` : ""} · Table View`;
    case "series":
      return `${content.attribute} · Chart View`;
    case "location":
      return content.title;
    case "scenario-change":
      return `${scenarioLabel(content.scenario)} · ${content.attribute}`;
  }
}

const ICON = {
  catalog: LuTable,
  entities: LuTable,
  series: LuChartLine,
  location: LuMapPin,
  "scenario-change": LuGitCompareArrows,
};

export function TableDrawer() {
  const content = useProjectStore((s) => s.tableDrawer);
  const record = useProjectStore((s) => s.record);
  const closeTableDrawer = useProjectStore((s) => s.closeTableDrawer);
  const Icon = content ? ICON[content.kind] : LuTable;
  const title = content
    ? drawerTitle(
        content,
        (carrier) => record?.carriers[carrier]?.niceName || carrier,
        (name) => record?.info.revisions.find((revision) => revision.name === name)?.label ?? name,
      )
    : "";

  return (
    <Drawer.Root
      open={content !== null}
      onOpenChange={(open) => {
        if (!open) closeTableDrawer();
      }}
      modal={false}
      disablePointerDismissal
      snapPoints={SNAP_POINTS}
      defaultSnapPoint={SNAP_POINTS[1]}
      snapToSequentialPoints
    >
      <Drawer.Portal>
        <Drawer.Viewport className="pointer-events-none fixed inset-0 z-30 flex touch-none items-end justify-center">
          <Drawer.Popup className="drawer-popup border-surface-600 bg-surface-800 pointer-events-auto relative flex max-h-[92vh] w-full touch-none flex-col rounded-t-lg border-t shadow-2xl shadow-black/50 outline-none">
            <div className="bg-surface-600 hover:bg-accent-500 mx-auto mt-1.5 h-1 w-10 shrink-0 cursor-row-resize touch-none rounded-full transition-colors" />
            <div className="border-surface-600 flex h-8 shrink-0 cursor-row-resize touch-none items-center justify-between border-b px-3 select-none">
              <div className="text-surface-200 flex min-w-0 items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
                <Icon size={12} className="shrink-0" />
                <span className="truncate" title={title}>
                  {title}
                </span>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <Drawer.Close className="text-surface-400 hover:text-surface-100 outline-none">
                  <LuX size={14} />
                </Drawer.Close>
              </div>
            </div>
            <Drawer.Content className="min-h-0 flex-1 touch-auto overflow-y-auto overscroll-contain text-[12px]">
              {content?.kind === "entities" ? (
                <EntityTable
                  key={`${content.ctype}\n${content.carrier}`}
                  ctype={content.ctype}
                  carrier={content.carrier}
                />
              ) : content?.kind === "series" ? (
                <SeriesChart
                  entity={content.entity}
                  attribute={content.attribute}
                  bus={content.bus}
                />
              ) : content?.kind === "location" ? (
                <LocationView locations={content.locations} />
              ) : content?.kind === "scenario-change" ? (
                <ScenarioChangeTable
                  key={`${content.scenario}\n${content.attribute}`}
                  scenario={content.scenario}
                  attribute={content.attribute}
                />
              ) : (
                <DummyTable />
              )}
            </Drawer.Content>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
