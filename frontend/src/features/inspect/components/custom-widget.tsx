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
import { LuCopy, LuSlidersHorizontal } from "react-icons/lu";
import type { Run } from "../../project/data/runs";
import { runLabel } from "../../project/data/inspect-results";
import {
  AGGREGATE_LABELS,
  queryFilteredBy,
  runQuery,
  type QueryResult,
} from "../../project/lib/custom-query";
import {
  CARRIER_GROUPS,
  carrierGroupOf,
  useInspectFilters,
} from "../../project/lib/inspect-filters";
import { regionFeatures } from "../../project/lib/record-geo";
import {
  BAR_COLOR,
  CARRIER_COLORS,
  formatValue,
  useChartColors,
} from "../../project/lib/use-widget-chart";
import { categoryData, type WidgetData } from "../../project/lib/widget-data";
import type { CustomItem, CustomWidgetState } from "../../project/lib/widget-sets";
import type { ViewState } from "../../project/store/types";
import { useProjectStore } from "../../project/store/project-store";
import { useAppStore } from "../../home/store";
import { CustomWidgetEditor } from "./custom-widget-editor";
import { EChart } from "../../project/components/echart";
import { WidgetCard } from "./widget-card";
import { WidgetIconButton } from "./widget-icon-button";

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

function seriesColor(name: string, index: number) {
  const group = carrierGroupOf(name);
  return (
    NAMED_COLORS[name] ??
    CARRIER_COLORS[name] ??
    (group ? CARRIER_GROUPS.find((item) => item.id === group)?.color : undefined) ??
    SERIES_PALETTE[index % SERIES_PALETTE.length]
  );
}

function formatAmount(value: number) {
  return value !== 0 && Math.abs(value) < 1
    ? value.toLocaleString(undefined, { maximumSignificantDigits: 3 })
    : formatValue(value);
}

/** The title a widget falls back to: "Supply by carrier". */
function customWidgetTitle(state: Pick<CustomWidgetState, "title" | "query">, tableLabel: string) {
  if (state.title.trim()) return state.title.trim();
  const [x, series] = state.query.groupBy;
  return `${tableLabel}${x ? ` by ${x.replaceAll("_", " ")}` : ""}${series ? ` and ${series.replaceAll("_", " ")}` : ""}`;
}

function valueRange(results: QueryResult[]): [number, number] {
  const values = results
    .flatMap((result) => result.series.flatMap((item) => item.values))
    .filter((value): value is number => value !== null);
  if (values.length === 0) return [0, 1];
  return [Math.min(0, ...values), Math.max(0, ...values)];
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

function useChartOption(
  result: QueryResult,
  chart: CustomWidgetState["chart"],
  range: [number, number],
): EChartsOption {
  const colors = useChartColors();
  return useMemo(() => {
    const { table, xColumn, seriesColumn, xLabels, series } = result;
    const isStacked = chart === "stacked-bar" || chart === "area";
    const isLine = chart === "line" || chart === "area";
    const hasLegend = seriesColumn !== null;
    const isTime = xColumn === "snapshot";
    return {
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 16, right: 16, top: hasLegend ? 40 : 20, bottom: 8, containLabel: true },
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
        name: xColumn?.replaceAll("_", " "),
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: colors.text,
          fontSize: 10,
          hideOverlap: true,
          ...(isTime && xLabels.length > 48
            ? { formatter: (label: string) => label.replace(/ \d\d:00$/, "") }
            : {}),
        },
      },
      yAxis: {
        type: "value",
        name: `${table.valueLabel} [${table.unit}]`,
        nameLocation: "middle",
        nameGap: 52,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        min: range[0],
        max: range[1],
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: series.map((item, index) => {
        const color = seriesColumn ? seriesColor(item.name, index) : BAR_COLOR;
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
  }, [result, chart, range, colors]);
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
  const theme = useAppStore((s) => s.theme);
  const record = useProjectStore((s) => s.record);
  const [hovered, setHovered] = useState<{ name: string; value: number | null } | null>(null);
  const areaData = useMemo(() => {
    const values = result.series[0]?.values ?? [];
    const valueByBus = new globalThis.Map(
      result.xLabels.map((label, index) => [label, values[index] ?? null]),
    );
    return {
      type: "FeatureCollection" as const,
      features: regionFeatures(record).map((area) => ({
        ...area,
        properties: { ...area.properties, value: valueByBus.get(area.properties.name) ?? null },
      })),
    };
  }, [record, result]);
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
      {areaData.features.length === 0 && (
        <div className="text-surface-400 pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-[12px]">
          No model areas loaded for this project.
        </div>
      )}
    </div>
  );
}

function Message({ children }: { children: string }) {
  return (
    <div className="text-surface-400 absolute inset-0 flex items-center justify-center px-6 text-center text-[12px]">
      {children}
    </div>
  );
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
  if (result.series.length === 0) return <Message>No data for the current filters.</Message>;
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
  selectedRun: Run,
  comparisonRun: Run,
): WidgetData {
  const unit = result.table.unit;
  const columns = [
    result.xColumn ?? "Value",
    ...(result.seriesColumn ? [result.seriesColumn] : []),
    `${runLabel(selectedRun)} [${unit}]`,
    `${runLabel(comparisonRun)} [${unit}]`,
    `Difference [${unit}]`,
  ];
  const rows = result.series.flatMap((item) => {
    const compared = comparison.series.find((other) => other.name === item.name);
    return result.xLabels.map((label, index) => {
      const value = item.values[index];
      const comparedIndex = comparison.xLabels.indexOf(label);
      const comparedValue = compared && comparedIndex >= 0 ? compared.values[comparedIndex] : null;
      const difference =
        value !== null && comparedValue !== null
          ? Math.round((value - comparedValue) * 1000) / 1000
          : null;
      return [label, ...(result.seriesColumn ? [item.name] : []), value, comparedValue, difference];
    });
  });
  return { columns, rows };
}

export function CustomWidget({
  item,
  onChange,
  onDuplicate,
  selectedRun,
  comparisonRun,
  startsEditing,
}: {
  item: CustomItem;
  onChange: (patch: Partial<CustomWidgetState>) => void;
  onDuplicate: () => void;
  selectedRun: Run;
  comparisonRun: Run | null;
  startsEditing: boolean;
}) {
  const { filters, allBuses } = useInspectFilters();
  const [isEditing, setEditing] = useState(startsEditing);
  const primary = useMemo(
    () => runQuery(item.query, { filters, allBuses, resultId: selectedRun.id }),
    [item.query, filters, allBuses, selectedRun],
  );
  const compared = useMemo(
    () =>
      comparisonRun
        ? runQuery(item.query, { filters, allBuses, resultId: comparisonRun.id })
        : null,
    [item.query, filters, allBuses, comparisonRun],
  );
  const result = "error" in primary ? null : primary;
  const comparison = compared && !("error" in compared) ? compared : null;
  const results = useMemo(
    () => [result, comparison].filter((entry): entry is QueryResult => entry !== null),
    [result, comparison],
  );
  // One value scale for both results, so equal heights and shades mean equal values.
  const range = useMemo(
    () =>
      item.chart === "stacked-bar" || item.chart === "area"
        ? stackedRange(results)
        : valueRange(results),
    [results, item.chart],
  );
  const title = customWidgetTitle(item, result?.table.label ?? "Custom widget");
  const problem = shapeProblem(item);

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

  const subtitle =
    item.subtitle.trim() ||
    `${AGGREGATE_LABELS[item.query.aggregate]} of ${result?.table.valueLabel.toLowerCase() ?? "value"} [${result?.table.unit ?? ""}] · ${item.mode === "sql" ? "SQL" : "custom"} widget`;
  const setMapViewState = (mapViewState: ViewState) => onChange({ mapViewState });

  const panel = (entry: QueryResult, run: Run, other: QueryResult | null, otherRun: Run | null) => (
    <div key={run.id} className="flex min-h-0 min-w-0 flex-1 flex-col">
      {comparisonRun && (
        <div className="text-surface-300 mb-1 truncate text-[11px] font-medium">
          {runLabel(run)}
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <ResultView
          state={item}
          result={entry}
          comparison={other}
          comparisonName={otherRun ? runLabel(otherRun) : ""}
          range={range}
          onMapViewStateChange={setMapViewState}
        />
      </div>
    </div>
  );

  return (
    <WidgetCard
      title={`${title}: ${runLabel(selectedRun)}`}
      subtitle={subtitle}
      filteredBy={queryFilteredBy(item.query)}
      data={data}
      // A single number needs little room until it's being edited.
      size={isEditing ? "tall" : item.chart === "number" ? "compact" : "regular"}
      sidePanel={
        isEditing ? (
          <CustomWidgetEditor state={item} onChange={onChange} onClose={() => setEditing(false)} />
        ) : undefined
      }
      action={
        <>
          <WidgetIconButton
            icon={LuSlidersHorizontal}
            label={isEditing ? "Close editor" : "Edit widget"}
            ariaLabel={isEditing ? "Close editor" : `Edit ${title}`}
            pressed={isEditing}
            onClick={() => setEditing((editing) => !editing)}
          />
          <WidgetIconButton
            icon={LuCopy}
            label="Duplicate widget"
            ariaLabel={`Duplicate ${title}`}
            onClick={onDuplicate}
          />
        </>
      }
    >
      {"error" in primary ? (
        <Message>{primary.error}</Message>
      ) : problem ? (
        <Message>{problem}</Message>
      ) : (
        <div className="absolute inset-0 flex gap-3 pt-2">
          {panel(primary, selectedRun, comparison, comparisonRun)}
          {comparison && comparisonRun && panel(comparison, comparisonRun, null, null)}
        </div>
      )}
    </WidgetCard>
  );
}
