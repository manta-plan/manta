import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import {
  busShare,
  carrierAllowed,
  snapshotShare,
  useInspectFilters,
} from "../../project/lib/inspect-filters";
import { BAR_COLOR, formatValue, useChartColors } from "../../project/lib/use-widget-chart";
import { categoryData, pairData } from "../../project/lib/widget-data";
import { EChart } from "../../project/components/echart";
import { WidgetCard } from "./widget-card";
import { EMISSIONS_BY_SECTOR } from "../../project/data/inspect-dummy-data";
import { useResultVariation } from "../../project/lib/result-comparison";

// The "Emissions & Policy" built-in inspection: whether the result meets its climate
// targets, after PyPSA's CO2 global constraint and its shadow price. Values
// are fixed placeholders, not solver output.

const EMITTING_COLOR = "#e0703a";
const REMOVAL_COLOR = "#3fae6a";
const CAPTURED_COLOR = "#3fae6a";

const NET_EMISSIONS = EMISSIONS_BY_SECTOR.reduce((sum, [, value]) => sum + value, 0);

// Mt CO2/a per planning year: net emissions against the CO2 limit.
const EMISSIONS_VS_CAP: [string, number, number][] = [
  ["2030", 1650, 1700],
  ["2035", 820, 820],
  ["2040", NET_EMISSIONS, NET_EMISSIONS],
];

// €/t, the CO2 limit's shadow price per planning year.
const CO2_PRICE: [string, number][] = [
  ["2030", 95],
  ["2035", 185],
  ["2040", 310],
];

// TWh of fossil fuel burned, split by whether its CO2 is captured.
const FOSSIL_FUEL_USE: [string, number, number][] = [
  ["Oil", 2690, 0],
  ["Gas", 1130, 380],
  ["Coal", 120, 20],
  ["Lignite", 60, 0],
];

// Filtered totals can be a single hour's worth, so small values keep
// significant digits instead of rounding to 0.
function formatAmount(value: number) {
  return Math.abs(value) > 0 && Math.abs(value) < 10
    ? value.toLocaleString(undefined, { maximumSignificantDigits: 3 })
    : formatValue(value);
}

function NoData() {
  return (
    <div className="text-surface-400 absolute inset-0 flex items-center justify-center text-[12px]">
      No data for the current filters.
    </div>
  );
}

function useBaseOption(unit: string) {
  const colors = useChartColors();
  return useMemo(
    () => ({
      colors,
      base: {
        backgroundColor: "transparent",
        textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
        tooltip: {
          trigger: "axis" as const,
          axisPointer: { type: "shadow" as const },
          backgroundColor: colors.tooltipBackground,
          borderColor: colors.axisLine,
          textStyle: { color: colors.strongText, fontSize: 11 },
          valueFormatter: (value: unknown) => `${formatAmount(Number(value))} ${unit}`,
        },
        legend: {
          right: 0,
          top: 4,
          textStyle: { color: colors.text, fontSize: 11 },
          itemWidth: 10,
          itemHeight: 10,
        },
      },
      categoryAxis: {
        type: "category" as const,
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: colors.text, fontSize: 10, interval: 0 },
      },
      valueAxis: {
        type: "value" as const,
        name: unit,
        nameLocation: "middle" as const,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
    }),
    [colors, unit],
  );
}

export function EmissionsBySectorChart({ resultName }: { resultName: string }) {
  const { base, categoryAxis, valueAxis } = useBaseOption("Mt CO2/a");
  const { filters, allBuses } = useInspectFilters();
  // The selected buses' share of each sector, over the selected snapshots.
  const vary = useResultVariation();
  const rows = useMemo(() => {
    const share = busShare(filters, allBuses);
    return EMISSIONS_BY_SECTOR.map(([sector, value]): [string, number] => [
      sector,
      vary(sector, value) * share * snapshotShare(filters, sector),
    ]);
  }, [filters, allBuses, vary]);
  const net = rows.reduce((sum, [, value]) => sum + value, 0);
  const option: EChartsOption = useMemo(
    () => ({
      ...base,
      grid: { left: 16, right: 24, top: 16, bottom: 40, containLabel: true },
      xAxis: { ...valueAxis, nameGap: 28 },
      yAxis: { ...categoryAxis, inverse: true, data: rows.map(([sector]) => sector) },
      series: [
        {
          type: "bar",
          name: "Emissions",
          barMaxWidth: 18,
          data: rows.map(([, value]) => ({
            value,
            itemStyle: { color: value < 0 ? REMOVAL_COLOR : EMITTING_COLOR },
          })),
        },
      ],
    }),
    [base, categoryAxis, valueAxis, rows],
  );

  return (
    <WidgetCard
      title={`CO2 emissions by sector: ${resultName}`}
      subtitle={`Removals from BECCS and direct air capture count negative · net ${formatAmount(net)} Mt CO2${filters.snapshots.mode === "all" ? "/a" : " in the selected snapshots"}`}
      filteredBy={["bus", "snapshot"]}
      data={pairData(
        "Sector",
        `Emissions [Mt CO2${filters.snapshots.mode === "all" ? "/a" : ""}]`,
        rows,
      )}
    >
      <EChart option={option} />
    </WidgetCard>
  );
}

export function EmissionsVsCapChart({ resultName }: { resultName: string }) {
  const { colors, base, categoryAxis, valueAxis } = useBaseOption("Mt CO2/a");
  const { filters, allBuses } = useInspectFilters();
  // Planning years, not snapshots: only the bus filter applies, as the
  // selected buses' share of both net emissions and the limit.
  const share = busShare(filters, allBuses);
  const vary = useResultVariation();
  // The limit is policy, the same in every result; net emissions can't exceed it.
  const net = useMemo(
    () => EMISSIONS_VS_CAP.map(([year, value, cap]) => Math.min(cap, vary(year, value)) * share),
    [vary, share],
  );
  const option: EChartsOption = useMemo(
    () => ({
      ...base,
      grid: { left: 64, right: 16, top: 32, bottom: 32 },
      legend: { ...base.legend, data: ["Net emissions", "CO2 limit"] },
      xAxis: { ...categoryAxis, data: EMISSIONS_VS_CAP.map(([year]) => year) },
      yAxis: { ...valueAxis, nameGap: 48 },
      series: [
        {
          type: "bar",
          name: "Net emissions",
          barMaxWidth: 64,
          itemStyle: { color: BAR_COLOR },
          data: net,
        },
        {
          type: "line",
          name: "CO2 limit",
          symbolSize: 7,
          lineStyle: { type: "dashed", color: colors.strongText },
          itemStyle: { color: colors.strongText },
          data: EMISSIONS_VS_CAP.map(([, , cap]) => cap * share),
        },
      ],
    }),
    [base, categoryAxis, valueAxis, colors, share, net],
  );
  const bindingYears = EMISSIONS_VS_CAP.filter(
    ([, , cap], index) => net[index] >= cap * share - 1e-9,
  ).map(([year]) => year);

  return (
    <WidgetCard
      title={`Emissions vs CO2 limit: ${resultName}`}
      subtitle={`${bindingYears.length > 0 ? `Limit binding in ${bindingYears.join(" and ")} — net emissions sit exactly on the cap` : "Net emissions stay below the limit"}${share < 1 ? " · selected buses’ share of both" : ""}`}
      filteredBy={["bus"]}
      data={categoryData(
        "Planning year",
        EMISSIONS_VS_CAP.map(([year]) => year),
        [
          { name: "Net emissions", values: net },
          { name: "CO2 limit", values: EMISSIONS_VS_CAP.map(([, , cap]) => cap * share) },
        ],
        "Mt CO2/a",
      )}
    >
      <EChart option={option} />
    </WidgetCard>
  );
}

export function Co2PriceChart({ resultName }: { resultName: string }) {
  const { colors, base, categoryAxis, valueAxis } = useBaseOption("€/t");
  const vary = useResultVariation();
  const prices = useMemo(
    () => CO2_PRICE.map(([year, price]): [string, number] => [year, Math.round(vary(year, price))]),
    [vary],
  );
  const latest = prices[prices.length - 1];
  const option: EChartsOption = useMemo(
    () => ({
      ...base,
      tooltip: { ...base.tooltip, axisPointer: { type: "line" } },
      grid: { left: 64, right: 16, top: 32, bottom: 32 },
      xAxis: { ...categoryAxis, boundaryGap: false, data: prices.map(([year]) => year) },
      yAxis: { ...valueAxis, nameGap: 48 },
      series: [
        {
          type: "line",
          name: "CO2 price",
          symbolSize: 8,
          itemStyle: { color: BAR_COLOR },
          areaStyle: { color: BAR_COLOR, opacity: 0.12 },
          label: {
            show: true,
            position: "top",
            color: colors.strongText,
            fontSize: 11,
            formatter: ({ value }) => `${formatValue(Number(value))} €/t`,
          },
          data: prices.map(([, price]) => price),
        },
      ],
    }),
    [base, categoryAxis, valueAxis, colors, prices],
  );

  return (
    <WidgetCard
      title={`CO2 shadow price: ${resultName}`}
      subtitle={`Marginal cost of the CO2 limit · ${formatValue(latest[1])} €/t in ${latest[0]}`}
      data={pairData("Planning year", "CO2 shadow price [€/t]", prices)}
    >
      <EChart option={option} />
    </WidgetCard>
  );
}

export function FossilFuelUseChart({ resultName }: { resultName: string }) {
  const { base, categoryAxis, valueAxis } = useBaseOption("TWh");
  const { filters, allBuses } = useInspectFilters();
  const vary = useResultVariation();
  const rows = useMemo(() => {
    const share = busShare(filters, allBuses);
    return FOSSIL_FUEL_USE.filter(([fuel]) => carrierAllowed(filters, fuel)).map(
      ([fuel, emitted, captured]): [string, number, number] => {
        const scale = share * snapshotShare(filters, fuel);
        return [
          fuel,
          vary(`${fuel}|emitted`, emitted) * scale,
          vary(`${fuel}|captured`, captured) * scale,
        ];
      },
    );
  }, [filters, allBuses, vary]);
  const option: EChartsOption = useMemo(
    () => ({
      ...base,
      grid: { left: 64, right: 16, top: 32, bottom: 32 },
      legend: { ...base.legend, data: ["Emitted", "Captured"] },
      xAxis: { ...categoryAxis, data: rows.map(([fuel]) => fuel) },
      yAxis: { ...valueAxis, nameGap: 48 },
      series: [
        {
          type: "bar",
          name: "Emitted",
          stack: "fuel",
          barMaxWidth: 64,
          itemStyle: { color: EMITTING_COLOR },
          data: rows.map(([, emitted]) => emitted),
        },
        {
          type: "bar",
          name: "Captured",
          stack: "fuel",
          barMaxWidth: 64,
          itemStyle: { color: CAPTURED_COLOR },
          data: rows.map(([, , captured]) => captured),
        },
      ],
    }),
    [base, categoryAxis, valueAxis, rows],
  );

  return (
    <WidgetCard
      title={`Fossil fuel use: ${resultName}`}
      subtitle="Fuel burned by type, split by whether its CO2 is captured"
      filteredBy={["bus", "snapshot", "carrier"]}
      data={categoryData(
        "Fuel",
        rows.map(([fuel]) => fuel),
        [
          { name: "Emitted", values: rows.map(([, emitted]) => emitted) },
          { name: "Captured", values: rows.map(([, , captured]) => captured) },
        ],
        "TWh",
      )}
    >
      {rows.length > 0 ? <EChart option={option} /> : <NoData />}
    </WidgetCard>
  );
}
