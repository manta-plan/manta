import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import Map, {
  AttributionControl,
  Layer,
  ScaleControl,
  Source,
  type MapLayerMouseEvent,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  SNAPSHOT_COUNT,
  describeSnapshots,
  snapshotCount,
  snapshotLevel,
  snapshotShare,
  useInspectFilters,
  type FilterDimension,
  type InspectFilters,
} from "../../project/lib/inspect-filters";
import { branchFeatures } from "../../project/lib/record-geo";
import { BAR_COLOR, formatValue, useChartColors } from "../../project/lib/use-widget-chart";
import { NODAL, type ViewState } from "../../project/store/types";
import { useProjectStore } from "../../project/store/project-store";
import { useAppStore } from "../../home/store";
import { pairData } from "../../project/lib/widget-data";
import { EChart } from "../../project/components/echart";
import { WidgetCard } from "./widget-card";
import {
  useResultVariation,
  useSharedWidgetState,
  type Vary,
} from "../../project/lib/result-comparison";

// The "Transmission & Congestion" built-in inspection: where the grid is the
// bottleneck, after PyPSA's line loading and flow statistics. Values are
// fixed placeholders, not solver output. The page's bus and snapshot filters
// reshape them; the carrier filter doesn't, since every line here carries
// electricity.

const CARTO_BASEMAP_STYLE = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

const IMPORT_COLOR = "#f2a541";
const LOADING_LAYER_ID = "line-loading";
// Green → amber → red as average loading climbs towards the thermal limit.
const LOADING_STOPS: [number, string][] = [
  [0, "#2c7bb6"],
  [40, "#abd9e9"],
  [60, "#fee090"],
  [80, "#fc8d59"],
  [100, "#d73027"],
];

// Hours per year at ≥ 95% loading.
const CONGESTION_HOURS: [string, number][] = [
  ["DE – PL", 3120],
  ["FR – ES", 2870],
  ["DE – NL", 2410],
  ["IT – CH", 2280],
  ["GB – FR", 1960],
  ["NO – DK", 1740],
  ["AT – IT", 1520],
  ["SE – FI", 1310],
  ["BE – NL", 1180],
  ["CZ – SK", 940],
];

// TWh/a, net: positive is export, negative is import.
const NET_FLOWS: [string, number][] = [
  ["FR", 62.4],
  ["NO", 38.1],
  ["SE", 27.6],
  ["ES", 14.2],
  ["DK", 6.8],
  ["PL", -9.5],
  ["NL", -13.7],
  ["BE", -18.9],
  ["IT", -34.2],
  ["DE", -41.3],
];

// €/MWh, time-averaged price difference across the corridor.
const PRICE_SPREAD: [string, number][] = [
  ["DE – PL", 18.4],
  ["FR – ES", 14.9],
  ["IT – CH", 22.7],
  ["DE – NL", 9.6],
  ["GB – FR", 16.3],
  ["NO – DK", 11.2],
  ["AT – IT", 19.8],
  ["SE – FI", 7.4],
];

function hashString(text: string) {
  let hash = 0;
  for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) % 100003;
  return hash;
}

// Dummy average loading per branch, 10–100%.
function lineLoading(id: string) {
  return 10 + (hashString(id) % 900) / 10;
}

// Corridors and flows are named by country. A bus whose name starts with a
// country code ("DE0 12") reaches them through that country; buses without
// one can't, so those widgets then don't claim the bus filter.
function busCountries(buses: string[]) {
  return new Set(
    buses
      .map((bus) => /^([A-Z]{2})/.exec(bus)?.[1])
      .filter((code): code is string => code !== undefined),
  );
}

function corridorCountries(corridor: string) {
  return corridor.split(" – ");
}

interface FilteredBars {
  data: [string, number][];
  filteredBy: FilterDimension[];
}

// Keeps rows touching the selected buses' countries, when they map to any.
function filterByBusCountry(
  rows: [string, number][],
  filters: InspectFilters,
): { rows: [string, number][]; byBus: boolean } {
  const countries = busCountries(filters.buses);
  const known = new Set(rows.flatMap(([label]) => corridorCountries(label)));
  if (![...countries].some((country) => known.has(country))) return { rows, byBus: false };
  return {
    rows: rows.filter(([label]) =>
      corridorCountries(label).some((country) => countries.has(country)),
    ),
    byBus: true,
  };
}

const round = (value: number) => Math.round(value * 10) / 10;

function congestionHours(filters: InspectFilters, vary: Vary): FilteredBars {
  const { rows, byBus } = filterByBusCountry(CONGESTION_HOURS, filters);
  const hours = snapshotCount(filters.snapshots);
  // Congested hours shrink with the window and lean on its season, capped at the window itself.
  const data = rows.map(([corridor, perYear]): [string, number] => [
    corridor,
    Math.min(
      hours,
      Math.round(vary(corridor, perYear) * (hours / SNAPSHOT_COUNT) * snapshotLevel(filters)),
    ),
  ]);
  return { data, filteredBy: ["snapshot", ...(byBus ? ["bus" as const] : [])] };
}

function netFlows(filters: InspectFilters, vary: Vary): FilteredBars {
  const { rows, byBus } = filterByBusCountry(NET_FLOWS, filters);
  // A slice of the year moves far less than a TWh, so it reads in GWh.
  const unitScale = filters.snapshots.mode === "all" ? 1 : 1000;
  return {
    data: rows.map(([country, flow]): [string, number] => [
      country,
      round(vary(country, flow) * snapshotShare(filters) * unitScale),
    ]),
    filteredBy: ["snapshot", ...(byBus ? ["bus" as const] : [])],
  };
}

function priceSpread(filters: InspectFilters, vary: Vary): FilteredBars {
  const { rows, byBus } = filterByBusCountry(PRICE_SPREAD, filters);
  return {
    data: rows.map(([corridor, spread]): [string, number] => [
      corridor,
      round(vary(corridor, spread) * snapshotLevel(filters)),
    ]),
    filteredBy: ["snapshot", ...(byBus ? ["bus" as const] : [])],
  };
}

function TransmissionBarChart({
  title,
  subtitle,
  labelHeader,
  valueName,
  unit,
  data,
  filteredBy,
  horizontal = false,
  signed = false,
}: {
  title: string;
  subtitle: string;
  labelHeader: string;
  valueName: string;
  unit: string;
  data: [string, number][];
  filteredBy: FilterDimension[];
  horizontal?: boolean;
  signed?: boolean;
}) {
  const colors = useChartColors();

  const option: EChartsOption = useMemo(() => {
    const categoryAxis = {
      type: "category" as const,
      data: data.map(([label]) => label),
      inverse: horizontal,
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisTick: { show: false },
      axisLabel: { color: colors.text, fontSize: 10, interval: 0 },
    };
    const valueAxis = {
      type: "value" as const,
      name: unit,
      nameLocation: "middle" as const,
      nameGap: horizontal ? 28 : 48,
      nameTextStyle: { color: colors.text, fontSize: 11 },
      axisLabel: { color: colors.text, fontSize: 10 },
      splitLine: { lineStyle: { color: colors.splitLine } },
    };

    return {
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: horizontal
        ? { left: 16, right: 24, top: 16, bottom: 40, containLabel: true }
        : { left: 64, right: 16, top: signed ? 32 : 20, bottom: 32 },
      legend: signed
        ? {
            right: 0,
            top: 4,
            data: ["Export", "Import"],
            textStyle: { color: colors.text, fontSize: 11 },
            itemWidth: 10,
            itemHeight: 10,
          }
        : undefined,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        formatter: (params) => {
          const item =
            (Array.isArray(params) ? params : [params]).find(
              (entry) => entry.value !== "-" && entry.value !== null,
            ) ?? (Array.isArray(params) ? params[0] : params);
          const value = Number(item.value);
          const label = signed ? (value >= 0 ? "Net export" : "Net import") : title.split(":")[0];
          return `<div style="font-weight:600;margin-bottom:4px">${item.name}</div>${label}: <b>${formatValue(Math.abs(value))}</b> ${unit}`;
        },
      },
      xAxis: horizontal ? valueAxis : categoryAxis,
      yAxis: horizontal ? categoryAxis : valueAxis,
      // Signed flows split into two series so exports and imports get their
      // own colour and legend entry; '-' leaves the other series' bar empty.
      series: signed
        ? [
            {
              type: "bar" as const,
              name: "Export",
              stack: "flow",
              data: data.map(([, value]) => (value >= 0 ? value : "-")),
              itemStyle: { color: BAR_COLOR },
              barMaxWidth: 48,
            },
            {
              type: "bar" as const,
              name: "Import",
              stack: "flow",
              data: data.map(([, value]) => (value < 0 ? value : "-")),
              itemStyle: { color: IMPORT_COLOR },
              barMaxWidth: 48,
            },
          ]
        : [
            {
              type: "bar" as const,
              data: data.map(([, value]) => value),
              itemStyle: { color: BAR_COLOR },
              barMaxWidth: horizontal ? 18 : 64,
            },
          ],
    };
  }, [colors, data, horizontal, signed, title, unit]);

  return (
    <WidgetCard
      title={title}
      subtitle={subtitle}
      filteredBy={filteredBy}
      data={pairData(labelHeader, `${valueName} [${unit}]`, data)}
    >
      {data.length > 0 ? (
        <EChart option={option} />
      ) : (
        <div className="text-surface-400 absolute inset-0 flex items-center justify-center text-[12px]">
          No data for the current filters.
        </div>
      )}
    </WidgetCard>
  );
}

export function LineLoadingMap({ resultName }: { resultName: string }) {
  const theme = useAppStore((s) => s.theme);
  const record = useProjectStore((s) => s.record);
  const { filters } = useInspectFilters();
  // Seeded from the main map so the widget opens over the area the user was looking at.
  // Both results' maps move together when comparing.
  const [viewState, setViewState] = useSharedWidgetState<ViewState>(
    "viewState",
    () => useProjectStore.getState().viewState,
  );
  const vary = useResultVariation();
  const [hoveredLine, setHoveredLine] = useState<{
    id: string;
    name: string;
    loading: number;
  } | null>(null);

  // AC lines between locations; every branch type if the record has no Lines.
  // Loading follows the season of the selected snapshots; lines touching a
  // selected bus stay bright and the rest dim.
  const lineData = useMemo(() => {
    const branches = record ? branchFeatures(record, NODAL) : [];
    const lines = branches.some((branch) => branch.properties.ctype === "Line")
      ? branches.filter((branch) => branch.properties.ctype === "Line")
      : branches;
    const level = snapshotLevel(filters);
    const selected = new Set(filters.buses);
    return {
      type: "FeatureCollection" as const,
      features: lines.map((line) => {
        const [, , from, to] = line.properties.id.split("|");
        const highlighted = selected.size === 0 || selected.has(from) || selected.has(to);
        return {
          ...line,
          properties: {
            ...line.properties,
            name: `${from} – ${to}`,
            loading: round(
              Math.min(100, vary(line.properties.id, lineLoading(line.properties.id)) * level),
            ),
            highlighted,
          },
        };
      }),
    };
  }, [record, filters, vary]);

  // Only lines touching a selected bus, when the bus filter is on.
  const data = useMemo(
    () =>
      pairData(
        "Line",
        "Average loading [%]",
        lineData.features
          .filter((line) => line.properties.highlighted)
          .map((line): [string, number] => [line.properties.name, line.properties.loading]),
      ),
    [lineData],
  );

  const lineColor = [
    "interpolate",
    ["linear"],
    ["get", "loading"],
    ...LOADING_STOPS.flat(),
  ] as unknown as string;
  const lineWidth = [
    "interpolate",
    ["linear"],
    ["get", "loading"],
    0,
    1,
    100,
    5,
  ] as unknown as number;

  const handleMouseMove = (event: MapLayerMouseEvent) => {
    const properties = event.features?.[0]?.properties;
    setHoveredLine(
      properties
        ? {
            id: properties.id as string,
            name: properties.name as string,
            loading: Number(properties.loading),
          }
        : null,
    );
  };

  return (
    <WidgetCard
      title={`Average line loading: ${resultName}`}
      subtitle={`Time-averaged flow as a share of each line's thermal limit${filters.snapshots.mode === "all" ? "" : ` · ${describeSnapshots(filters.snapshots)}`}`}
      filteredBy={["bus", "snapshot"]}
      data={data}
    >
      <div className="absolute inset-0 mt-2 overflow-hidden">
        <Map
          {...viewState}
          onMove={(event) => setViewState(event.viewState)}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredLine(null)}
          interactiveLayerIds={[LOADING_LAYER_ID]}
          cursor={hoveredLine ? "pointer" : undefined}
          mapStyle={CARTO_BASEMAP_STYLE[theme]}
          attributionControl={false}
          style={{ position: "absolute", inset: 0 }}
        >
          <Source id="line-loading" type="geojson" data={lineData}>
            <Layer
              id={LOADING_LAYER_ID}
              type="line"
              layout={{ "line-cap": "round" }}
              paint={{
                "line-color": lineColor,
                "line-width": lineWidth,
                "line-opacity": [
                  "case",
                  ["==", ["get", "id"], hoveredLine?.id ?? ""],
                  1,
                  ["get", "highlighted"],
                  0.85,
                  0.12,
                ],
              }}
            />
          </Source>
          <ScaleControl position="bottom-left" />
          <AttributionControl position="bottom-right" compact />
        </Map>

        <div className="border-surface-600 bg-surface-900/90 pointer-events-none absolute top-2 left-2 w-44 rounded border px-2 py-1.5 backdrop-blur">
          <div className="text-surface-400 text-[10px] font-medium tracking-wide uppercase">
            Loading [%]
          </div>
          <div
            className="mt-1 h-2 rounded-sm"
            style={{
              background: `linear-gradient(to right, ${LOADING_STOPS.map(([, color]) => color).join(", ")})`,
            }}
          />
          <div className="text-surface-400 mt-0.5 flex justify-between text-[10px] tabular-nums">
            <span>0</span>
            <span>100</span>
          </div>
          {hoveredLine && (
            <div className="border-surface-700 mt-1.5 border-t pt-1.5 text-[11px]">
              <div className="text-surface-100 truncate font-medium">{hoveredLine.name}</div>
              <div className="text-surface-300 tabular-nums">
                {formatValue(hoveredLine.loading)}% average loading
              </div>
            </div>
          )}
        </div>

        {lineData.features.length === 0 && (
          <div className="text-surface-400 pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-[12px]">
            No model areas loaded for this project.
          </div>
        )}
      </div>
    </WidgetCard>
  );
}

function usePeriod() {
  const { filters } = useInspectFilters();
  const isWholeYear = filters.snapshots.mode === "all";
  return {
    filters,
    vary: useResultVariation(),
    isWholeYear,
    period: isWholeYear ? "per year" : `in ${describeSnapshots(filters.snapshots)}`,
  };
}

export function CongestionHoursChart({ resultName }: { resultName: string }) {
  const { filters, vary, isWholeYear, period } = usePeriod();
  const congestion = useMemo(() => congestionHours(filters, vary), [filters, vary]);
  return (
    <TransmissionBarChart
      title={`Congestion hours by corridor: ${resultName}`}
      labelHeader="Corridor"
      valueName="Congestion hours"
      subtitle={`Hours ${period} at or above 95% of the thermal limit, most congested corridors`}
      unit={isWholeYear ? "h/a" : "h"}
      data={congestion.data}
      filteredBy={congestion.filteredBy}
      horizontal
    />
  );
}

export function CrossBorderFlowsChart({ resultName }: { resultName: string }) {
  const { filters, vary, isWholeYear, period } = usePeriod();
  const flows = useMemo(() => netFlows(filters, vary), [filters, vary]);
  return (
    <TransmissionBarChart
      title={`Net cross-border flows: ${resultName}`}
      labelHeader="Country"
      valueName="Net export"
      subtitle={`Net exports (positive) and imports (negative) by country ${period}`}
      unit={isWholeYear ? "TWh/a" : "GWh"}
      data={flows.data}
      filteredBy={flows.filteredBy}
      signed
    />
  );
}

export function PriceSpreadChart({ resultName }: { resultName: string }) {
  const { filters, vary, isWholeYear } = usePeriod();
  const spread = useMemo(() => priceSpread(filters, vary), [filters, vary]);
  return (
    <TransmissionBarChart
      title={`Price spread across congested corridors: ${resultName}`}
      labelHeader="Corridor"
      valueName="Price spread"
      subtitle={`Time-averaged price difference between the regions at each end${isWholeYear ? "" : ` · ${describeSnapshots(filters.snapshots)}`}`}
      unit="€/MWh"
      data={spread.data}
      filteredBy={spread.filteredBy}
    />
  );
}
