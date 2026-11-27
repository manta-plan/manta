// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

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
import { LuCopy, LuDiff, LuSlidersHorizontal } from "react-icons/lu";
import type { InspectResult } from "../lib/result-source";

/** What a widget needs of a result: its id to query, its label to show. */
type ResultRef = Pick<InspectResult, "id" | "label">;
import {
  AGGREGATE_LABELS,
  isPlaceholderCondition,
  queryFilteredBy,
  querySql,
  type QueryResult,
} from "../lib/custom-query";
import { useInspectFilters } from "../lib/inspect-filters";
import type { ResultTableInfo } from "../lib/result-source";
import {
  useResultCatalogue,
  useResultQuery,
  type LoadState,
  type QueryState,
} from "../lib/use-result-data";
import { CARRIER_GROUPS, carrierGroupOf } from "../lib/inspect-filters";
import { useRegionFeatures } from "../lib/record-geo";
import { NO_REGIONS, useHasMapRegions } from "../lib/map-availability";
import {
  BAR_COLOR,
  CARRIER_COLORS,
  formatValue,
  useChartColors,
} from "../../project/lib/use-widget-chart";
import { categoryData, type WidgetData } from "../lib/widget-data";
import type { CustomItem, CustomWidgetState } from "../lib/widget-sets";
import { useWidgetColorScheme } from "../lib/widget-presentation";
import type { ViewState } from "../../project/store/types";
import { useProjectStore } from "../../project/store/project-store";
import { CustomWidgetEditor } from "./custom-widget-editor";
import { effectiveAggregate } from "../lib/record-result-source";
import { EChart } from "../../project/components/echart";
import { WidgetCard } from "./widget-card";
import { WidgetIconButton } from "./widget-icon-button";
import { WidgetMessage, WidgetNoMap } from "../../../components/widget-states";

// A widget the user builds from a query of a result table. It draws bars,
// lines, areas, a table, a single number or a bus map, and with a
// comparison it draws the compared result alongside.

const CARTO_BASEMAP_STYLE = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};
const VIRIDIS = [
  "#440154",
  "#482878",
  "#3e4989",
  "#31688e",
  "#26828e",
  "#1f9e89",
  "#35b779",
  "#6ece58",
  "#b5de2b",
  "#fde725",
];
const SERIES_PALETTE = [
  "#5699ff",
  "#f2a541",
  "#3fae6a",
  "#e0703a",
  "#b07cf0",
  "#3dbfb0",
  "#e45f8c",
  "#9aa5b1",
];
const NAMED_COLORS: Record<string, string> = { Capex: BAR_COLOR, Opex: "#f2a541" };

// The record's own carrier colours come first (PyPSA-Eur's tell CCGT from OCGT, solar from solar-hsat).
function seriesColor(name: string, index: number, recordColors: Record<string, string>) {
  const group = carrierGroupOf(name);
  return (
    NAMED_COLORS[name] ??
    recordColors[name] ??
    CARRIER_COLORS[name] ??
    (group ? CARRIER_GROUPS.find((item) => item.id === group)?.color : undefined) ??
    SERIES_PALETTE[index % SERIES_PALETTE.length]
  );
}

/** The record's carrier colours, by carrier name. */
function useRecordCarrierColors(): Record<string, string> {
  const carriers = useProjectStore((s) => s.record?.carriers);
  return useMemo(
    () =>
      Object.fromEntries(
        Object.values(carriers ?? {}).flatMap((carrier) =>
          carrier.color ? [[carrier.carrier, carrier.color]] : [],
        ),
      ),
    [carriers],
  );
}

function formatAmount(value: number) {
  return value !== 0 && Math.abs(value) < 1
    ? value.toLocaleString(undefined, { maximumSignificantDigits: 3 })
    : formatValue(value);
}

/** The title a widget falls back to: "Supply by carrier". */
function customWidgetTitle(state: Pick<CustomWidgetState, "title" | "query">, valueLabel: string) {
  if (state.title.trim()) return state.title.trim();
  const [x, series] = state.query.groupBy;
  return `${valueLabel}${x ? ` by ${x.replaceAll("_", " ")}` : ""}${series ? ` and ${series.replaceAll("_", " ")}` : ""}`;
}

/** The periods a widget's values cover, for its subtitle: "2050", "2040 and 2050, a year on average", or every period's average year. */
function periodContext(
  item: CustomItem,
  table: ResultTableInfo,
  period: string | null,
  periods: string[],
): string | null {
  if (
    !table.columns.includes("period") ||
    item.query.groupBy.includes("period") ||
    periods.length === 0
  )
    return null;
  const followsFilter = item.query.where.some(
    (condition) => isPlaceholderCondition(condition) && condition.placeholder === "period",
  );
  const picked = item.query.where.flatMap((condition) =>
    !isPlaceholderCondition(condition) &&
    condition.column === "period" &&
    condition.values.length > 0
      ? [condition.values]
      : [],
  );
  const shown =
    followsFilter && period !== null
      ? [period]
      : picked.length > 0
        ? picked.reduce((kept, values) => kept.filter((value) => values.includes(value)))
        : periods;
  if (shown.length === 1) return shown[0];
  const span =
    shown.length === periods.length
      ? `${periods[0]}–${periods[periods.length - 1]}`
      : shown.join(", ");
  // A sum over several periods is shown as an average year; averages are over all their hours.
  return effectiveAggregate(table.kind, item.query.aggregate) === "sum"
    ? `average year of ${span}`
    : span;
}

/** The selected result's labels, then the compared result's extra ones. */
function unionLabels(primary: QueryResult, other: QueryResult): string[] {
  return [...primary.xLabels, ...other.xLabels.filter((label) => !primary.xLabels.includes(label))];
}

/** The series names of both results, the selected one's first. */
function unionSeriesNames(primary: QueryResult, other: QueryResult): string[] {
  return [
    ...primary.series.map((item) => item.name),
    ...other.series
      .map((item) => item.name)
      .filter((name) => !primary.series.some((item) => item.name === name)),
  ];
}

/** A series' value at a label, or null when the result has no such series or label. */
function valueAt(result: QueryResult, name: string, label: string): number | null {
  const position = result.xLabels.indexOf(label);
  return position < 0
    ? null
    : (result.series.find((item) => item.name === name)?.values[position] ?? null);
}

/** The selected result minus the compared one, label by label and series by series (a missing value counts as nothing there). */
function differenceOf(primary: QueryResult, other: QueryResult): QueryResult {
  const labels = unionLabels(primary, other);
  return {
    ...primary,
    xLabels: labels,
    series: unionSeriesNames(primary, other).map((name) => ({
      name,
      values: labels.map((label) => {
        const [mine, theirs] = [valueAt(primary, name, label), valueAt(other, name, label)];
        return mine === null && theirs === null
          ? null
          : Math.round(((mine ?? 0) - (theirs ?? 0)) * 1000) / 1000;
      }),
    })),
  };
}

/** The other result's labels in the selected one's order (its extra ones after), so two charts side by side line up. */
function alignedTo(primary: QueryResult, other: QueryResult): QueryResult {
  const order = [
    ...primary.xLabels,
    ...other.xLabels.filter((label) => !primary.xLabels.includes(label)),
  ];
  const index = new globalThis.Map(other.xLabels.map((label, position) => [label, position]));
  return {
    ...other,
    xLabels: order,
    series: other.series.map((item) => ({
      ...item,
      values: order.map((label) => (index.has(label) ? item.values[index.get(label)!] : null)),
    })),
  };
}

function valueRange(results: QueryResult[]): [number, number] {
  const values = results
    .flatMap((result) => result.series.flatMap((item) => item.values))
    .filter((value): value is number => value !== null);
  if (values.length === 0) return [0, 1];
  return [Math.min(0, ...values), Math.max(0, ...values)];
}

/** The values' own span, for a colour scale (a map's), which needn't start at zero. */
function dataRange(results: QueryResult[]): [number, number] {
  const values = results
    .flatMap((result) => result.series.flatMap((item) => item.values))
    .filter((value): value is number => value !== null);
  if (values.length === 0) return [0, 1];
  const [low, high] = [Math.min(...values), Math.max(...values)];
  return low === high ? [low - 1, high + 1] : [low, high];
}

function stackedRange(results: QueryResult[]): [number, number] {
  let low = 0;
  let high = 0;
  for (const result of results) {
    result.xLabels.forEach((_, index) => {
      const values = result.series.map((item) => item.values[index] ?? 0);
      high = Math.max(
        high,
        values.filter((value) => value > 0).reduce((sum, value) => sum + value, 0),
      );
      low = Math.min(
        low,
        values.filter((value) => value < 0).reduce((sum, value) => sum + value, 0),
      );
    });
  }
  return [low, high];
}

/** A round number at or above `value`: 1, 2, 2.5 or 5 times a power of ten. */
function niceCeil(value: number) {
  if (value <= 0) return 0;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => value / power <= candidate + 1e-9) ?? 10;
  return step * power;
}

function useChartOption(
  result: QueryResult,
  chart: CustomWidgetState["chart"],
  range: [number, number],
): EChartsOption {
  const colors = useChartColors();
  const recordColors = useRecordCarrierColors();
  return useMemo(() => {
    const { table, xColumn, seriesColumn, xLabels, series } = result;
    const isStacked = chart === "stacked-bar" || chart === "area";
    const isLine = chart === "line" || chart === "area";
    const hasLegend = seriesColumn !== null;
    const isTime = xColumn === "snapshot";
    return {
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      // Room above the plot for the value axis's name and unit.
      grid: { left: 16, right: 16, top: hasLegend ? 52 : 30, bottom: 8, containLabel: true },
      legend: hasLegend
        ? {
            type: "scroll",
            left: 0,
            right: 0,
            top: 4,
            textStyle: { color: colors.text, fontSize: 11 },
            pageTextStyle: { color: colors.text },
            itemWidth: 10,
            itemHeight: 10,
          }
        : undefined,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: isLine ? "line" : "shadow" },
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        valueFormatter: (value) =>
          value === null || value === undefined
            ? "—"
            : `${formatAmount(Number(value))} ${table.unit}`,
      },
      xAxis: {
        type: "category",
        boundaryGap: !isLine,
        data: xLabels,
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        // Every category keeps its label (turned when they're many); only a time axis thins out.
        axisLabel: isTime
          ? {
              color: colors.text,
              fontSize: 10,
              hideOverlap: true,
              ...(xLabels.length > 48
                ? { formatter: (label: string) => label.replace(/ \d\d:00$/, "") }
                : {}),
            }
          : {
              color: colors.text,
              fontSize: 10,
              interval: 0,
              rotate: xLabels.length > 6 ? 35 : 0,
              width: 96,
              overflow: "truncate",
            },
      },
      yAxis: {
        type: "value",
        // Above the axis, where it's never clipped and prints too.
        name: `${table.valueLabel} [${table.unit}]`,
        nameLocation: "end",
        nameGap: 10,
        nameTextStyle: { color: colors.text, fontSize: 11, align: "left" },
        // Round ends, shared by both results' charts when comparing.
        min: -niceCeil(-range[0]),
        max: niceCeil(range[1]),
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: series.map((item, index) => {
        const color = seriesColumn ? seriesColor(item.name, index, recordColors) : BAR_COLOR;
        return isLine
          ? {
              type: "line" as const,
              name: item.name,
              data: item.values,
              stack: isStacked ? "total" : undefined,
              symbol: "none",
              lineStyle: { width: chart === "area" ? 0 : 1.5, color },
              areaStyle: chart === "area" ? { color, opacity: 0.9 } : undefined,
              itemStyle: { color },
            }
          : {
              type: "bar" as const,
              name: item.name,
              data: item.values,
              stack: isStacked ? "total" : undefined,
              barMaxWidth: 120,
              itemStyle: { color, borderRadius: isStacked ? 0 : [2, 2, 0, 0] },
            };
      }),
    };
  }, [result, chart, range, colors, recordColors]);
}

function ResultChartPanel({
  result,
  chart,
  range,
}: {
  result: QueryResult;
  chart: CustomWidgetState["chart"];
  range: [number, number];
}) {
  const option = useChartOption(result, chart, range);
  return <EChart option={option} />;
}

function ResultTablePanel({ result }: { result: QueryResult }) {
  return (
    <div className="absolute inset-0 overflow-auto text-[12px]">
      <table className="w-full border-collapse">
        <thead className="bg-surface-900 text-surface-400 sticky top-0 text-left">
          <tr>
            {result.xColumn && (
              <th className="border-surface-700 border-b px-3 py-1.5 font-medium whitespace-nowrap">
                {result.xColumn}
              </th>
            )}
            {result.series.map((item) => (
              <th
                key={item.name}
                className="border-surface-700 border-b px-3 py-1.5 text-right font-medium whitespace-nowrap"
              >
                {item.name} [{result.table.unit}]
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.xLabels.map((label, index) => (
            <tr key={label} className="text-surface-200 hover:bg-surface-800">
              {result.xColumn && (
                <td className="border-surface-800 text-surface-100 border-b px-3 py-1 font-mono whitespace-nowrap">
                  {label}
                </td>
              )}
              {result.series.map((item) => (
                <td
                  key={item.name}
                  className="border-surface-800 text-surface-300 border-b px-3 py-1 text-right whitespace-nowrap tabular-nums"
                >
                  {item.values[index] === null ? "—" : formatAmount(item.values[index]!)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NumberPanel({
  result,
  aggregate,
  comparison,
  comparisonName,
}: {
  result: QueryResult;
  aggregate: string;
  comparison: QueryResult | null;
  comparisonName: string;
}) {
  const value = result.series[0]?.values[0] ?? null;
  const comparedValue = comparison?.series[0]?.values[0] ?? null;
  const delta = value !== null && comparedValue !== null ? value - comparedValue : null;
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center">
      <div className="text-surface-400 text-[11px] tracking-wide uppercase">
        {aggregate} of {result.table.valueLabel.toLowerCase()}
      </div>
      <div className="text-surface-50 text-[32px] leading-none font-semibold tabular-nums">
        {value === null ? "—" : formatAmount(value)}
        <span className="text-surface-400 ml-1.5 text-[16px] font-medium">{result.table.unit}</span>
      </div>
      {delta !== null && (
        <div
          className={`text-[12px] tabular-nums ${delta > 0 ? "text-ok-500" : delta < 0 ? "text-danger-500" : "text-surface-400"}`}
        >
          {delta > 0 ? "+" : ""}
          {formatAmount(delta)} {result.table.unit} vs {comparisonName}
        </div>
      )}
    </div>
  );
}

/** The bounding box of the regions' polygons, as [[west, south], [east, north]]. */
function regionBounds(
  features: { geometry: { coordinates: unknown } }[],
): [[number, number], [number, number]] | null {
  let [west, south, east, north] = [Infinity, Infinity, -Infinity, -Infinity];
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number" && typeof value[1] === "number") {
      west = Math.min(west, value[0]);
      east = Math.max(east, value[0]);
      south = Math.min(south, value[1]);
      north = Math.max(north, value[1]);
    } else value.forEach(visit);
  };
  features.forEach((feature) => visit(feature.geometry.coordinates));
  return Number.isFinite(west)
    ? [
        [west, south],
        [east, north],
      ]
    : null;
}

function ResultMapPanel({
  result,
  domain,
  viewState,
  onViewStateChange,
}: {
  result: QueryResult;
  domain: [number, number];
  viewState: ViewState;
  onViewStateChange: (viewState: ViewState) => void;
}) {
  const theme = useWidgetColorScheme();
  const regions = useRegionFeatures();
  const [hovered, setHovered] = useState<{ name: string; value: number | null } | null>(null);
  const areaData = useMemo(() => {
    const values = result.series[0]?.values ?? [];
    const valueByBus = new globalThis.Map(
      result.xLabels.map((label, index) => [label, values[index] ?? null]),
    );
    return {
      type: "FeatureCollection" as const,
      features: regions.map((area) => ({
        ...area,
        properties: { ...area.properties, value: valueByBus.get(area.properties.name) ?? null },
      })),
    };
  }, [regions, result]);
  // Opens on the record's regions, wherever the main map was.
  const bounds = useMemo(() => regionBounds(areaData.features), [areaData]);
  const [low, high] = domain;
  const span = high - low || 1;
  const fillColor = [
    "case",
    ["==", ["get", "value"], null],
    "rgba(0,0,0,0)",
    [
      "interpolate",
      ["linear"],
      ["get", "value"],
      ...VIRIDIS.flatMap((color, index) => [low + (span * index) / (VIRIDIS.length - 1), color]),
    ],
  ] as unknown as string;

  const handleMouseMove = (event: MapLayerMouseEvent) => {
    const properties = event.features?.[0]?.properties;
    setHovered(
      properties
        ? {
            name: properties.name as string,
            value:
              properties.value === null ||
              properties.value === undefined ||
              properties.value === "null"
                ? null
                : Number(properties.value),
          }
        : null,
    );
  };

  return (
    <div className="absolute inset-0 overflow-hidden">
      <Map
        {...viewState}
        onLoad={(event) => bounds && event.target.fitBounds(bounds, { padding: 24, duration: 0 })}
        onMove={(event) => onViewStateChange(event.viewState)}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHovered(null)}
        interactiveLayerIds={["custom-values-fill"]}
        cursor={hovered ? "pointer" : undefined}
        mapStyle={CARTO_BASEMAP_STYLE[theme]}
        attributionControl={false}
        style={{ position: "absolute", inset: 0 }}
      >
        <Source id="custom-values" type="geojson" data={areaData}>
          <Layer
            id="custom-values-fill"
            type="fill"
            paint={{
              "fill-color": fillColor,
              "fill-opacity": ["case", ["==", ["get", "name"], hovered?.name ?? ""], 0.95, 0.8],
            }}
          />
          <Layer
            id="custom-values-outline"
            type="line"
            paint={{ "line-color": "#ffffff", "line-width": 0.5, "line-opacity": 0.6 }}
          />
        </Source>
        <ScaleControl position="bottom-left" />
        <AttributionControl position="bottom-right" compact />
      </Map>
      <div className="border-surface-600 bg-surface-900/90 pointer-events-none absolute top-2 left-2 w-44 rounded border px-2 py-1.5 backdrop-blur">
        <div className="text-surface-400 truncate text-[10px] font-medium tracking-wide uppercase">
          {result.table.valueLabel} [{result.table.unit}]
        </div>
        <div
          className="mt-1 h-2 rounded-sm"
          style={{ background: `linear-gradient(to right, ${VIRIDIS.join(", ")})` }}
        />
        <div className="text-surface-400 mt-0.5 flex justify-between text-[10px] tabular-nums">
          <span>{formatAmount(low)}</span>
          <span>{formatAmount(high)}</span>
        </div>
        {hovered && (
          <div className="border-surface-700 mt-1.5 border-t pt-1.5 text-[11px]">
            <div className="text-surface-100 truncate font-medium">{hovered.name}</div>
            <div className="text-surface-300 tabular-nums">
              {hovered.value === null
                ? "Not in the query"
                : `${formatAmount(hovered.value)} ${result.table.unit}`}
            </div>
          </div>
        )}
      </div>
      {areaData.features.length === 0 && <WidgetNoMap reason={NO_REGIONS} />}
    </div>
  );
}

// Both results' queries as one state: loading until both answer, failing if either does.
function combinedState(primary: QueryState, compared: QueryState | null): LoadState {
  const states = compared ? [primary, compared] : [primary];
  const failed = states.find((state) => state.status === "error");
  if (failed)
    return {
      status: "error",
      error: failed.error,
      retry: () => states.forEach((state) => state.status === "error" && state.retry()),
    };
  if (states.some((state) => state.status === "loading")) return { status: "loading" };
  return {
    status: "ready",
    isRefreshing: states.some((state) => state.status === "ready" && state.isRefreshing),
  };
}

// Why the chart can't draw this query's shape, if it can't.
function shapeProblem(state: CustomWidgetState): string | null {
  const [x, series] = state.query.groupBy;
  if (state.chart === "number" && x)
    return "A single number needs a query without GROUP BY. Remove the X axis, or pick another chart.";
  if (state.chart === "map" && (x !== "bus" || series))
    return "A map needs bus on the X axis and no series.";
  if (state.chart !== "number" && state.chart !== "table" && !x)
    return "Pick an X axis to draw this chart, or show it as a single number.";
  return null;
}

function ResultView({
  state,
  result,
  comparison,
  comparisonName,
  range,
  onMapViewStateChange,
}: {
  state: CustomWidgetState;
  result: QueryResult;
  comparison: QueryResult | null;
  comparisonName: string;
  range: [number, number];
  onMapViewStateChange: (viewState: ViewState) => void;
}) {
  if (result.series.length === 0)
    return <WidgetMessage>No data for the current filters.</WidgetMessage>;
  if (state.chart === "table") return <ResultTablePanel result={result} />;
  if (state.chart === "number")
    return (
      <NumberPanel
        result={result}
        aggregate={AGGREGATE_LABELS[state.query.aggregate]}
        comparison={comparison}
        comparisonName={comparisonName}
      />
    );
  if (state.chart === "map")
    return (
      <ResultMapPanel
        result={result}
        domain={range}
        viewState={state.mapViewState}
        onViewStateChange={onMapViewStateChange}
      />
    );
  return <ResultChartPanel result={result} chart={state.chart} range={range} />;
}

// With a comparison: the selected and compared result, then the difference.
function comparisonData(
  result: QueryResult,
  comparison: QueryResult,
  selectedRun: ResultRef,
  comparisonRun: ResultRef,
): WidgetData {
  const unit = result.table.unit;
  const columns = [
    result.xColumn ?? "Value",
    ...(result.seriesColumn ? [result.seriesColumn] : []),
    `${selectedRun.label} [${unit}]`,
    `${comparisonRun.label} [${unit}]`,
    `Difference [${unit}]`,
  ];
  const labels = unionLabels(result, comparison);
  const rows = unionSeriesNames(result, comparison).flatMap((name) =>
    labels.map((label) => {
      const value = valueAt(result, name, label);
      const comparedValue = valueAt(comparison, name, label);
      const difference =
        value !== null && comparedValue !== null
          ? Math.round((value - comparedValue) * 1000) / 1000
          : null;
      return [label, ...(result.seriesColumn ? [name] : []), value, comparedValue, difference];
    }),
  );
  return { columns, rows };
}

export function CustomWidget({
  item,
  onChange,
  onDuplicate,
  selectedRun,
  comparisonRun,
  startsEditing,
  builtIn = false,
}: {
  item: CustomItem;
  onChange: (patch: Partial<CustomWidgetState>) => void;
  onDuplicate: () => void;
  selectedRun: ResultRef;
  comparisonRun: ResultRef | null;
  startsEditing: boolean;
  /** A built-in widget: drawn the same, with its editor read-only (changed through "Edit a copy") and no duplicate. */
  builtIn?: boolean;
}) {
  const { tables, periods } = useResultCatalogue();
  const { filters } = useInspectFilters();
  const [isEditing, setEditing] = useState(startsEditing);
  const table = tables.find((entry) => entry.name === item.query.table) ?? null;
  const hasMap = useHasMapRegions();
  const noMap = item.chart === "map" && !hasMap;
  const problem = table
    ? noMap
      ? NO_REGIONS
      : shapeProblem(item)
    : `This result has no "${item.query.table}" table. Pick another in the editor.`;
  // Nothing to ask while the query can't be drawn.
  const query = problem ? null : item.query;
  const primaryState = useResultQuery(query, selectedRun.id);
  const comparedState = useResultQuery(query, comparisonRun?.id ?? null);
  const result = primaryState.status === "ready" ? primaryState.data : null;
  const comparedData =
    comparisonRun && comparedState.status === "ready" ? comparedState.data : null;
  const comparison = useMemo(
    () =>
      comparedData && result && item.query.groupBy[0] !== "snapshot"
        ? alignedTo(result, comparedData)
        : comparedData,
    [comparedData, result, item.query.groupBy],
  );
  const loadState = problem
    ? undefined
    : combinedState(primaryState, comparisonRun ? comparedState : null);
  // When comparing, one chart of the difference instead of two side by side (a number already shows its delta).
  const [showDifference, setShowDifference] = useState(false);
  const canShowDifference =
    comparisonRun !== null && item.chart !== "number" && item.chart !== "table";
  const difference = useMemo(
    () =>
      showDifference && canShowDifference && result && comparedData
        ? differenceOf(result, alignedTo(result, comparedData))
        : null,
    [showDifference, canShowDifference, result, comparedData],
  );
  const results = useMemo(
    () =>
      difference
        ? [difference]
        : [result, comparison].filter((entry): entry is QueryResult => entry !== null),
    [difference, result, comparison],
  );
  // One value scale for both results, so equal heights and shades mean equal values.
  const range = useMemo(
    () =>
      item.chart === "stacked-bar" || item.chart === "area"
        ? stackedRange(results)
        : item.chart === "map"
          ? dataRange(results)
          : valueRange(results),
    [results, item.chart],
  );
  const title = customWidgetTitle(item, table?.valueLabel ?? "Custom widget");

  const data = useMemo<WidgetData>(() => {
    if (!result) return { columns: [], rows: [] };
    if (comparison && comparisonRun)
      return comparisonData(result, comparison, selectedRun, comparisonRun);
    return categoryData(
      result.xColumn ?? "Value",
      result.xLabels,
      result.series,
      result.table.unit,
    );
  }, [result, comparison, selectedRun, comparisonRun]);

  // Only SQL the builder couldn't have written makes it an SQL widget; looking at the SQL tab doesn't.
  const isSql = item.sql.trim() !== querySql(item.query).trim();
  const baseSubtitle =
    item.subtitle.trim() ||
    `${AGGREGATE_LABELS[table ? effectiveAggregate(table.kind, item.query.aggregate) : item.query.aggregate]} of ${table?.valueLabel.toLowerCase() ?? "value"}${table ? ` [${table.unit}]` : ""} · ${isSql ? "SQL" : "custom"} widget`;
  const shownPeriod = table ? periodContext(item, table, filters.period, periods) : null;
  const subtitle = shownPeriod ? `${baseSubtitle} · ${shownPeriod}` : baseSubtitle;
  const setMapViewState = (mapViewState: ViewState) => onChange({ mapViewState });

  const panel = (
    entry: QueryResult,
    run: ResultRef,
    other: QueryResult | null,
    otherRun: ResultRef | null,
  ) => (
    <div key={run.id} className="flex min-h-0 min-w-0 flex-1 flex-col">
      {comparisonRun && (
        <div className="text-surface-300 mb-1 truncate text-[11px] font-medium">{run.label}</div>
      )}
      <div className="relative min-h-0 flex-1">
        <ResultView
          state={item}
          result={entry}
          comparison={other}
          comparisonName={otherRun ? otherRun.label : ""}
          range={range}
          onMapViewStateChange={setMapViewState}
        />
      </div>
    </div>
  );

  return (
    <WidgetCard
      title={`${title}: ${selectedRun.label}${comparisonRun ? ` vs ${comparisonRun.label}` : ""}`}
      subtitle={subtitle}
      filteredBy={queryFilteredBy(item.query)}
      data={data}
      // A single number needs little room until it's being edited.
      size={isEditing ? "tall" : item.chart === "number" ? "compact" : "regular"}
      loadState={loadState}
      sidePanel={
        isEditing ? (
          <CustomWidgetEditor
            state={item}
            onChange={onChange}
            onClose={() => setEditing(false)}
            readOnly={builtIn}
          />
        ) : undefined
      }
      action={
        <>
          <WidgetIconButton
            icon={LuSlidersHorizontal}
            label={isEditing ? "Close editor" : builtIn ? "How it’s built" : "Edit widget"}
            ariaLabel={
              isEditing ? "Close editor" : builtIn ? `How ${title} is built` : `Edit ${title}`
            }
            pressed={isEditing}
            onClick={() => setEditing((editing) => !editing)}
          />
          {canShowDifference && (
            <WidgetIconButton
              icon={LuDiff}
              label={
                showDifference
                  ? "Show side by side"
                  : `Show the difference (${selectedRun.label} − ${comparisonRun.label})`
              }
              pressed={showDifference}
              onClick={() => setShowDifference((on) => !on)}
            />
          )}
          {!builtIn && (
            <WidgetIconButton
              icon={LuCopy}
              label="Duplicate widget"
              ariaLabel={`Duplicate ${title}`}
              onClick={onDuplicate}
            />
          )}
        </>
      }
    >
      {noMap && table ? (
        <WidgetNoMap
          reason={NO_REGIONS}
          hint="Pick another chart in the editor, such as a bar chart by bus."
        />
      ) : problem ? (
        <WidgetMessage>{problem}</WidgetMessage>
      ) : (
        result &&
        (difference && comparisonRun ? (
          <div className="absolute inset-0 flex gap-3 pt-2">
            {panel(
              difference,
              { id: "difference", label: `${selectedRun.label} − ${comparisonRun.label}` },
              null,
              null,
            )}
          </div>
        ) : (
          <div className="absolute inset-0 flex gap-3 pt-2">
            {panel(result, selectedRun, comparison, comparisonRun)}
            {comparison && comparisonRun && panel(comparison, comparisonRun, null, null)}
          </div>
        ))
      )}
    </WidgetCard>
  );
}
