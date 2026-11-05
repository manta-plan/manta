import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import {
  busShare,
  carrierAllowed,
  snapshotLevel,
  snapshotShare,
  useInspectFilters,
} from "../../project/lib/inspect-filters";
import {
  BAR_COLOR,
  CARRIER_COLORS,
  formatValue,
  useChartColors,
} from "../../project/lib/use-widget-chart";
import { categoryData, pairData } from "../../project/lib/widget-data";
import { EChart } from "../../project/components/echart";
import { BusPriceMap } from "./system-overview-widgets";
import { WidgetCard } from "./widget-card";

// The "Hydrogen & Sector Coupling" built-in inspection: how hydrogen, heat and
// transport lean on the power system. Values are fixed placeholders, not
// solver output.

const SUPPLY_COLOR = "#3fae6a";
const DEMAND_COLOR = "#e0703a";
const CAPACITY_FACTOR_COLOR = "#f2a541";

// TWh/a in 2040 — supply positive, uses negative; the two sides balance.
const H2_BALANCE: [string, number][] = [
  ["Electrolysis", 780],
  ["Imports", 210],
  ["SMR with CC", 120],
  ["Industry", -420],
  ["Fischer-Tropsch", -310],
  ["Shipping fuels", -140],
  ["Land transport", -95],
  ["H2 turbines", -80],
  ["Storage losses", -65],
];

// GW installed and average capacity factor (%) per country.
const ELECTROLYSIS_BY_COUNTRY: [string, number, number][] = [
  ["ES", 48, 52],
  ["DE", 41, 38],
  ["FR", 33, 44],
  ["IT", 27, 47],
  ["GB", 24, 41],
  ["PL", 15, 35],
  ["NL", 14, 39],
  ["SE", 12, 56],
  ["NO", 10, 61],
  ["PT", 9, 50],
];

// TWh/a of electricity drawn by coupled sectors per planning year.
const YEARS = ["2030", "2035", "2040"];
const COUPLED_DEMAND: { name: string; color: string; values: number[] }[] = [
  { name: "Heat pumps", color: CARRIER_COLORS["heat pump"], values: [180, 310, 420] },
  { name: "Electric vehicles", color: "#6b8fd6", values: [90, 240, 380] },
  { name: "Electrolysis", color: CARRIER_COLORS["H2 Electrolysis"], values: [120, 560, 1110] },
  { name: "Direct air capture", color: "#8b8b8b", values: [0, 60, 210] },
  { name: "Resistive heaters", color: "#c7a8e0", values: [40, 55, 70] },
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

export function H2BalanceChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters, allBuses } = useInspectFilters();
  // Rows are processes and sectors, not carriers, so only buses and
  // snapshots apply: the selected buses' share over the selected hours.
  const rows = useMemo(() => {
    const scale = busShare(filters, allBuses) * snapshotShare(filters, "H2");
    return H2_BALANCE.map(([name, value]): [string, number] => [name, value * scale]);
  }, [filters, allBuses]);

  const option: EChartsOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 16, right: 24, top: 16, bottom: 40, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params;
          const value = Number(item.value);
          return `${item.name}<br/>${value >= 0 ? "Supply" : "Use"}: <b>${formatAmount(Math.abs(value))}</b> TWh`;
        },
      },
      xAxis: {
        type: "value",
        name: filters.snapshots.mode === "all" ? "TWh/a" : "TWh",
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: rows.map(([name]) => name),
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: colors.text, fontSize: 10 },
      },
      series: [
        {
          type: "bar",
          data: rows.map(([, value]) => ({
            value,
            itemStyle: { color: value >= 0 ? SUPPLY_COLOR : DEMAND_COLOR },
          })),
          barMaxWidth: 18,
          label: {
            show: true,
            position: "right",
            color: colors.text,
            fontSize: 10,
            formatter: ({ value }) => formatAmount(Math.abs(Number(value))),
          },
        },
      ],
    }),
    [colors, rows, filters.snapshots.mode],
  );

  return (
    <WidgetCard
      title={`Hydrogen balance: ${resultName}`}
      subtitle="Where hydrogen comes from and where it goes · supply in green, uses in orange"
      filteredBy={["bus", "snapshot"]}
      data={pairData(
        "Process or use",
        `Hydrogen [TWh${filters.snapshots.mode === "all" ? "/a" : ""}]`,
        rows,
      )}
    >
      <EChart option={option} />
    </WidgetCard>
  );
}

export function ElectrolysisChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters, allBuses } = useInspectFilters();
  const hasHydrogen = carrierAllowed(filters, "H2 Electrolysis");
  const rows = useMemo(() => {
    // Buses named after a country (e.g. "DE0 1") keep that country at full
    // capacity and dim the rest; otherwise capacity is the selected buses' share.
    const pickedCountries = new Set(
      ELECTROLYSIS_BY_COUNTRY.map(([country]) => country).filter((country) =>
        filters.buses.some((bus) => bus.toUpperCase().startsWith(country)),
      ),
    );
    const share = pickedCountries.size > 0 ? 1 : busShare(filters, allBuses);
    // Seasonal level of the selected snapshots shifts how hard electrolysers run.
    const level = snapshotLevel(filters, "H2 Electrolysis");
    return ELECTROLYSIS_BY_COUNTRY.map(([country, capacity, capacityFactor]) => ({
      country,
      capacity: capacity * share,
      capacityFactor: Math.min(100, Math.round(capacityFactor * level * 10) / 10),
      isDimmed: pickedCountries.size > 0 && !pickedCountries.has(country),
    }));
  }, [filters, allBuses]);

  const option: EChartsOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 64, right: 64, top: 32, bottom: 32 },
      legend: {
        right: 0,
        top: 4,
        textStyle: { color: colors.text, fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        formatter: (params) => {
          const items = Array.isArray(params) ? params : [params];
          const [capacity, capacityFactor] = items;
          return `<div style="font-weight:600;margin-bottom:4px">${capacity.name}</div>${capacity.marker}Capacity: <b>${formatAmount(Number(capacity.value))}</b> GW<br/>${capacityFactor.marker}Capacity factor: <b>${formatValue(Number(capacityFactor.value))}</b>%`;
        },
      },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.country),
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: colors.text, fontSize: 10 },
      },
      yAxis: [
        {
          type: "value",
          name: "GW",
          nameLocation: "middle",
          nameGap: 40,
          nameTextStyle: { color: colors.text, fontSize: 11 },
          axisLabel: { color: colors.text, fontSize: 10 },
          splitLine: { lineStyle: { color: colors.splitLine } },
        },
        {
          type: "value",
          name: "Capacity factor (%)",
          nameLocation: "middle",
          nameGap: 40,
          nameTextStyle: { color: colors.text, fontSize: 11 },
          min: 0,
          max: 100,
          axisLabel: { color: colors.text, fontSize: 10 },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          type: "bar",
          name: "Capacity",
          data: rows.map((row) => ({
            value: row.capacity,
            itemStyle: { opacity: row.isDimmed ? 0.25 : 1 },
          })),
          itemStyle: { color: BAR_COLOR, borderRadius: [2, 2, 0, 0] },
          barMaxWidth: 48,
        },
        {
          type: "line",
          name: "Capacity factor",
          yAxisIndex: 1,
          data: rows.map((row) => row.capacityFactor),
          itemStyle: { color: CAPACITY_FACTOR_COLOR },
          lineStyle: { color: CAPACITY_FACTOR_COLOR, width: 2 },
          symbolSize: 6,
        },
      ],
    }),
    [colors, rows],
  );

  return (
    <WidgetCard
      title={`Electrolysis by country: ${resultName}`}
      subtitle={
        filters.snapshots.mode === "all"
          ? "Installed electrolyser capacity and how much of the year it runs"
          : "Installed electrolyser capacity and how hard it runs in the selected snapshots"
      }
      filteredBy={["bus", "snapshot", "carrier"]}
      data={{
        columns: ["Country", "Electrolyser capacity [GW]", "Capacity factor [%]"],
        // Only the picked countries, when the bus filter names some.
        rows: hasHydrogen
          ? rows
              .filter((row) => !row.isDimmed)
              .map((row) => [row.country, row.capacity, row.capacityFactor])
          : [],
      }}
    >
      {hasHydrogen ? <EChart option={option} /> : <NoData />}
    </WidgetCard>
  );
}

export function CoupledDemandChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters, allBuses } = useInspectFilters();
  // Planning years, not snapshots, and sectors rather than carriers: only
  // the selected buses' share applies.
  const share = busShare(filters, allBuses);

  const option: EChartsOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 64, right: 16, top: 32, bottom: 32 },
      legend: {
        right: 0,
        top: 4,
        textStyle: { color: colors.text, fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        formatter: (params) => {
          const items = Array.isArray(params) ? params : [params];
          const total = items.reduce((sum, item) => sum + Number(item.value), 0);
          return [
            `<div style="font-weight:600;margin-bottom:4px">${items[0].name}</div>`,
            ...items.map(
              (item) =>
                `${item.marker}${item.seriesName}: <b>${formatAmount(Number(item.value))}</b> TWh/a`,
            ),
            `Total: <b>${formatAmount(total)}</b> TWh/a`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: YEARS,
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: colors.text, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        name: "TWh/a",
        nameLocation: "middle",
        nameGap: 48,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: COUPLED_DEMAND.map((item) => ({
        type: "bar" as const,
        name: item.name,
        stack: "total",
        data: item.values.map((value) => value * share),
        itemStyle: { color: item.color },
        barMaxWidth: 96,
      })),
    }),
    [colors, share],
  );

  return (
    <WidgetCard
      title={`Electricity demand from coupled sectors: ${resultName}`}
      subtitle="New electricity demand from heat, transport, hydrogen and carbon removal per planning year"
      filteredBy={["bus"]}
      data={categoryData(
        "Planning year",
        YEARS,
        COUPLED_DEMAND.map((sector) => ({
          name: sector.name,
          values: sector.values.map((value) => value * share),
        })),
        "TWh/a",
      )}
    >
      <EChart option={option} />
    </WidgetCard>
  );
}

export function H2PriceMap({ resultName }: { resultName: string }) {
  return <BusPriceMap resultName={resultName} fixedCarrier="H2" />;
}
