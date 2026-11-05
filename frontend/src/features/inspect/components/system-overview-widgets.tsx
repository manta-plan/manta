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
import { regionFeatures } from "../../project/lib/record-geo";
import type { ViewState } from "../../project/store/types";
import { useProjectStore } from "../../project/store/project-store";
import { useAppStore } from "../../home/store";
import {
  BAR_COLOR,
  CARRIER_COLORS,
  formatValue,
  useChartColors,
} from "../../project/lib/use-widget-chart";
import {
  busShare,
  carrierAllowed,
  carrierGroupOf,
  snapshotLevel,
  snapshotShare,
  useInspectFilters,
  type FilterDimension,
  type InspectFilters,
} from "../../project/lib/inspect-filters";
import { categoryData, pairData, type WidgetData } from "../../project/lib/widget-data";
import { EChart } from "../../project/components/echart";
import { FormSelect } from "../../home/components/form-select";
import { WidgetCard } from "./widget-card";
import { GENERATOR_SUPPLY, WITHDRAWAL, busPrice } from "../../project/data/inspect-dummy-data";
import {
  useResultVariation,
  useSharedWidgetState,
  type Vary,
} from "../../project/lib/result-comparison";

// The "System Overview" built-in inspection: dummy versions of PyPSA statistics plots.
// Values are fixed placeholders, not solver output.

const CARTO_BASEMAP_STYLE = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

const INSTALLED_CAPACITY: { component: string; unit: string; carriers: [string, number][] }[] = [
  {
    component: "Generator",
    unit: "GW",
    carriers: [
      ["solar-pv-utility", 750],
      ["Onshore Wind", 550],
      ["solar-pv-rooftop", 450],
      ["biomass", 130],
      ["offwind-ac", 150],
      ["offwind-dc", 110],
      ["run of river", 60],
    ],
  },
  {
    component: "Link",
    unit: "GW",
    carriers: [
      ["electricity distribution grid", 760],
      ["H2 pipeline", 760],
      ["land transport oil", 480],
      ["DC", 370],
      ["nuclear", 310],
      ["H2 Electrolysis", 240],
      ["gas boiler", 230],
      ["Fischer-Tropsch", 210],
      ["heat pump", 200],
    ],
  },
  {
    component: "StorageUnit",
    unit: "GW",
    carriers: [
      ["hydro-phs", 7],
      ["Battery Storage", 30],
      ["hydro", 113],
      ["hydro-phs-pure", 5],
    ],
  },
  {
    component: "Store",
    unit: "GWh",
    carriers: [
      ["hydro-phs", 29400],
      ["H2 Store", 9100],
      ["hydro-phs-pure", 1200],
      ["home battery", 800],
      ["Battery Storage", 600],
    ],
  },
];

const PRICE_CARRIERS = [
  { value: "AC", label: "AC" },
  { value: "H2", label: "H2" },
];

const PRICE_RANGE: [number, number] = [0, 125];

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

// Narrow filters (one snapshot, one bus) leave totals well below 1.
function formatAmount(value: number) {
  return value !== 0 && Math.abs(value) < 1
    ? value.toLocaleString(undefined, { maximumSignificantDigits: 2 })
    : formatValue(value);
}

function NoFilteredData() {
  return (
    <div className="text-surface-400 absolute inset-0 flex items-center justify-center text-[12px]">
      No data for the current filters.
    </div>
  );
}

// Whether every label maps to a carrier group, so the carrier filter can apply.
function isCarrierLabelled(rows: [string, number][]) {
  return rows.every(([label]) => carrierGroupOf(label) !== null);
}

export function InstalledCapacityChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters, allBuses } = useInspectFilters();
  const vary = useResultVariation();
  // Capacities follow the bus share and the carrier filter, not the snapshots.
  const panels = useMemo(() => {
    const share = busShare(filters, allBuses);
    return INSTALLED_CAPACITY.map((panel) => ({
      ...panel,
      carriers: panel.carriers
        .filter(([carrier]) => carrierAllowed(filters, carrier))
        .map(([carrier, value]): [string, number] => [
          carrier,
          vary(`${panel.component}|${carrier}`, value) * share,
        ]),
    }));
  }, [filters, allBuses, vary]);
  const isEmpty = panels.every((panel) => panel.carriers.length === 0);
  // One row per component and carrier, since the panels don't share units.
  const data: WidgetData = useMemo(
    () => ({
      columns: ["Component", "Carrier", "Capacity", "Unit"],
      rows: panels.flatMap((panel) =>
        panel.carriers.map(([carrier, value]) => [panel.component, carrier, value, panel.unit]),
      ),
    }),
    [panels],
  );

  const option: EChartsOption = useMemo(() => {
    const panelCount = panels.length;
    // Panels share the width left of the legend, with a gap between them.
    const plotLeft = 6;
    const plotRight = 78;
    const gap = 3;
    const panelWidth = (plotRight - plotLeft - gap * (panelCount - 1)) / panelCount;
    const carriers = [
      ...new Set(panels.flatMap((panel) => panel.carriers.map(([carrier]) => carrier))),
    ];

    return {
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      tooltip: {
        trigger: "item",
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params;
          const data = item.data as { value: number; panel: number };
          const panel = panels[data.panel];
          return `${item.seriesName}<br/>${panel.component}: <b>${formatAmount(data.value)} ${panel.unit}</b>`;
        },
      },
      legend: {
        type: "scroll",
        orient: "vertical",
        right: 0,
        top: 8,
        bottom: 8,
        width: "18%",
        data: carriers,
        textStyle: { color: colors.text, fontSize: 11 },
        pageTextStyle: { color: colors.text },
        itemWidth: 10,
        itemHeight: 10,
      },
      title: panels.map((panel, index) => ({
        text: `${panel.component} [${panel.unit}]`,
        left: `${plotLeft + index * (panelWidth + gap) + panelWidth / 2}%`,
        top: 4,
        textAlign: "center",
        textStyle: { color: colors.text, fontSize: 11, fontWeight: 500 },
      })),
      grid: panels.map((_, index) => ({
        left: `${plotLeft + index * (panelWidth + gap)}%`,
        width: `${panelWidth}%`,
        top: 32,
        bottom: 16,
        containLabel: true,
      })),
      xAxis: panels.map((_, index) => ({
        type: "category",
        gridIndex: index,
        data: [""],
        axisTick: { show: false },
        axisLine: { lineStyle: { color: colors.axisLine } },
      })),
      yAxis: panels.map((_, index) => ({
        type: "value",
        gridIndex: index,
        name: index === 0 ? "Installed capacity" : undefined,
        nameLocation: "middle",
        nameGap: 44,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: {
          color: colors.text,
          fontSize: 10,
          formatter: (value: number) => (value >= 10000 ? `${value / 1000}k` : String(value)),
        },
        splitLine: { lineStyle: { color: colors.splitLine } },
      })),
      // One series per carrier per panel, stacked within its panel.
      series: panels.flatMap((panel, panelIndex) =>
        panel.carriers.map(([carrier, value]) => ({
          type: "bar" as const,
          name: carrier,
          xAxisIndex: panelIndex,
          yAxisIndex: panelIndex,
          stack: `panel-${panelIndex}`,
          barWidth: "80%",
          itemStyle: {
            color: CARRIER_COLORS[carrier] ?? BAR_COLOR,
            borderColor: colors.tooltipBackground,
            borderWidth: 0.5,
          },
          data: [{ value, panel: panelIndex }],
        })),
      ),
    };
  }, [colors, panels]);

  return (
    <WidgetCard
      title={`Installed capacity by component: ${resultName}`}
      subtitle="Links at bus0; excludes unbounded, placeholder (≥ 1 TW) and CO2 assets"
      filteredBy={["bus", "carrier"]}
      data={data}
    >
      {isEmpty ? <NoFilteredData /> : <EChart option={option} />}
    </WidgetCard>
  );
}

function CarrierBarChart({
  title,
  subtitle,
  valueLabel,
  data,
  seriesName,
  filteredBy,
}: {
  title: string;
  subtitle: string;
  valueLabel: string;
  data: [string, number][];
  seriesName?: string;
  filteredBy: FilterDimension[];
}) {
  const colors = useChartColors();

  const option: EChartsOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 64, right: seriesName ? 120 : 16, top: 20, bottom: 56 },
      legend: seriesName
        ? {
            orient: "vertical",
            right: 0,
            top: 8,
            data: [seriesName],
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
          const item = Array.isArray(params) ? params[0] : params;
          return `${item.name}: <b>${formatAmount(Number(item.value))} TWh</b>`;
        },
      },
      xAxis: {
        type: "category",
        name: "Carrier",
        nameLocation: "middle",
        nameGap: 36,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        data: data.map(([carrier]) => carrier),
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: colors.text, fontSize: 10, interval: 0 },
      },
      yAxis: {
        type: "value",
        name: valueLabel,
        nameLocation: "middle",
        nameGap: 48,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: [
        {
          type: "bar",
          name: seriesName,
          data: data.map(([, value]) => value),
          itemStyle: { color: BAR_COLOR, borderRadius: [2, 2, 0, 0] },
          barMaxWidth: 120,
        },
      ],
    }),
    [colors, data, seriesName, valueLabel],
  );

  return (
    <WidgetCard
      title={title}
      subtitle={subtitle}
      filteredBy={filteredBy}
      data={pairData("Carrier", valueLabel, data)}
    >
      {data.length === 0 ? <NoFilteredData /> : <EChart option={option} />}
    </WidgetCard>
  );
}

// `fixedCarrier` pins the map to one bus carrier and drops the picker.
export function BusPriceMap({
  resultName,
  fixedCarrier,
}: {
  resultName: string;
  fixedCarrier?: string;
}) {
  const theme = useAppStore((s) => s.theme);
  const record = useProjectStore((s) => s.record);
  // Both results' maps share the picked carrier and the viewport when comparing.
  const [selectedCarrier, setCarrier] = useSharedWidgetState("carrier", "AC");
  const carrier = fixedCarrier ?? selectedCarrier;
  // Seeded from the main map so the widget opens over the area the user was looking at.
  const [viewState, setViewState] = useSharedWidgetState<ViewState>(
    "viewState",
    () => useProjectStore.getState().viewState,
  );
  const [hoveredArea, setHoveredArea] = useState<{ name: string; price: number } | null>(null);
  const { filters } = useInspectFilters();
  // Prices follow the selected snapshots' seasonal level; the bus filter only
  // dims the areas it leaves out.
  const level = snapshotLevel(filters, carrier);
  const vary = useResultVariation();

  const areaData = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: regionFeatures(record).map((area) => ({
        ...area,
        properties: {
          ...area.properties,
          price: vary(carrier, busPrice(area.properties.name, carrier)) * level,
        },
      })),
    }),
    [record, carrier, level, vary],
  );

  // The selected buses only, when the bus filter is on.
  const data = useMemo(() => {
    const selected = new Set(filters.buses);
    const areas = areaData.features.filter(
      (area) => selected.size === 0 || selected.has(area.properties.name),
    );
    return categoryData(
      "Bus",
      areas.map((area) => area.properties.name),
      [
        {
          name: `${carrier} price`,
          values: areas.map((area) => Math.round(area.properties.price * 10) / 10),
        },
      ],
      "€/MWh",
    );
  }, [areaData, filters.buses, carrier]);

  const [low, high] = PRICE_RANGE;
  const fillColor = [
    "interpolate",
    ["linear"],
    ["get", "price"],
    ...VIRIDIS.flatMap((color, index) => [
      low + ((high - low) * index) / (VIRIDIS.length - 1),
      color,
    ]),
  ] as unknown as string;

  const handleMouseMove = (event: MapLayerMouseEvent) => {
    const properties = event.features?.[0]?.properties;
    setHoveredArea(
      properties ? { name: properties.name as string, price: Number(properties.price) } : null,
    );
  };

  return (
    <WidgetCard
      title={`Time-averaged ${fixedCarrier ? `${fixedCarrier} ` : ""}bus prices: ${resultName}`}
      subtitle="Colour scale spans prices below VoLL"
      filteredBy={["bus", "snapshot"]}
      data={data}
      action={
        fixedCarrier ? undefined : (
          <div className="w-24 shrink-0">
            <FormSelect
              value={carrier}
              onValueChange={setCarrier}
              options={PRICE_CARRIERS}
              ariaLabel="Bus carrier"
            />
          </div>
        )
      }
    >
      <div className="absolute inset-0 mt-2 overflow-hidden">
        <Map
          {...viewState}
          onMove={(event) => setViewState(event.viewState)}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredArea(null)}
          interactiveLayerIds={["bus-prices-fill"]}
          cursor={hoveredArea ? "pointer" : undefined}
          mapStyle={CARTO_BASEMAP_STYLE[theme]}
          attributionControl={false}
          style={{ position: "absolute", inset: 0 }}
        >
          <Source id="bus-prices" type="geojson" data={areaData}>
            <Layer
              id="bus-prices-fill"
              type="fill"
              paint={{
                "fill-color": fillColor,
                "fill-opacity": [
                  "case",
                  ["==", ["get", "name"], hoveredArea?.name ?? ""],
                  0.95,
                  filters.buses.length === 0
                    ? true
                    : ["in", ["get", "name"], ["literal", filters.buses]],
                  0.8,
                  0.12,
                ],
              }}
            />
            <Layer
              id="bus-prices-outline"
              type="line"
              paint={{ "line-color": "#ffffff", "line-width": 0.5, "line-opacity": 0.6 }}
            />
          </Source>
          <ScaleControl position="bottom-left" />
          <AttributionControl position="bottom-right" compact />
        </Map>

        <div className="border-surface-600 bg-surface-900/90 pointer-events-none absolute top-2 left-2 w-44 rounded border px-2 py-1.5 backdrop-blur">
          <div className="text-surface-400 text-[10px] font-medium tracking-wide uppercase">
            Price [€/MWh]
          </div>
          <div
            className="mt-1 h-2 rounded-sm"
            style={{ background: `linear-gradient(to right, ${VIRIDIS.join(", ")})` }}
          />
          <div className="text-surface-400 mt-0.5 flex justify-between text-[10px] tabular-nums">
            <span>{low}</span>
            <span>{high}</span>
          </div>
          {hoveredArea && (
            <div className="border-surface-700 mt-1.5 border-t pt-1.5 text-[11px]">
              <div className="text-surface-100 truncate font-medium">{hoveredArea.name}</div>
              <div className="text-surface-300 tabular-nums">
                {formatValue(hoveredArea.price)} €/MWh
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
    </WidgetCard>
  );
}

// Energy totals follow the bus share and each carrier's share of the selected
// snapshots; rows drop under the carrier filter when every label is a carrier.
function filterEnergyRows(
  rows: [string, number][],
  filters: InspectFilters,
  allBuses: string[],
  vary: Vary,
): [string, number][] {
  const share = busShare(filters, allBuses);
  return rows
    .filter(([label]) => !isCarrierLabelled(rows) || carrierAllowed(filters, label))
    .map(([label, value]) => [label, vary(label, value) * share * snapshotShare(filters, label)]);
}

const SUPPLY_FILTERED_BY: FilterDimension[] = isCarrierLabelled(GENERATOR_SUPPLY)
  ? ["bus", "snapshot", "carrier"]
  : ["bus", "snapshot"];
const WITHDRAWAL_FILTERED_BY: FilterDimension[] = isCarrierLabelled(WITHDRAWAL)
  ? ["bus", "snapshot", "carrier"]
  : ["bus", "snapshot"];

export function GeneratorSupplyChart({ resultName }: { resultName: string }) {
  const { filters, allBuses } = useInspectFilters();
  const vary = useResultVariation();
  const supply = useMemo(
    () => filterEnergyRows(GENERATOR_SUPPLY, filters, allBuses, vary),
    [filters, allBuses, vary],
  );
  return (
    <CarrierBarChart
      title={`Generator supply by carrier: ${resultName}`}
      subtitle="Largest carriers covering 95% of total supply"
      valueLabel="Supply [TWh]"
      data={supply}
      filteredBy={SUPPLY_FILTERED_BY}
    />
  );
}

export function WithdrawalChart({ resultName }: { resultName: string }) {
  const { filters, allBuses } = useInspectFilters();
  const vary = useResultVariation();
  const withdrawal = useMemo(
    () => filterEnergyRows(WITHDRAWAL, filters, allBuses, vary),
    [filters, allBuses, vary],
  );
  return (
    <CarrierBarChart
      title={`Withdrawal by carrier: ${resultName}`}
      subtitle="All loads and generators with negative output"
      valueLabel="Withdrawal [TWh]"
      data={withdrawal}
      seriesName="Load"
      filteredBy={WITHDRAWAL_FILTERED_BY}
    />
  );
}
