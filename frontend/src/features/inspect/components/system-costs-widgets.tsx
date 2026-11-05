import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { BAR_COLOR, formatValue, useChartColors } from "../../project/lib/use-widget-chart";
import {
  busShare,
  carrierAllowed,
  snapshotLevel,
  snapshotShare,
  useInspectFilters,
  type FilterDimension,
  type InspectFilters,
} from "../../project/lib/inspect-filters";
import { categoryData } from "../../project/lib/widget-data";
import { EChart } from "../../project/components/echart";
import { WidgetCard } from "./widget-card";
import { COST_BY_CARRIER, COST_BY_COMPONENT } from "../../project/data/inspect-dummy-data";
import { useResultVariation, type Vary } from "../../project/lib/result-comparison";

// The "System Costs" built-in inspection: where the system's money goes, after
// PyPSA's n.statistics capex/opex/market_value. Values are fixed
// placeholders, not solver output.

const CAPEX_COLOR = BAR_COLOR;
const OPEX_COLOR = "#f2a541";
const EXISTING_COLOR = "#8aa4c0";

// €/MWh: levelised cost against the price each carrier actually earns.
const LCOE_VS_MARKET_VALUE: [string, number, number][] = [
  ["solar-pv-utility", 32, 28],
  ["solar-pv-rooftop", 58, 30],
  ["Onshore Wind", 45, 48],
  ["offwind-ac", 62, 55],
  ["offwind-dc", 68, 57],
  ["run of river", 40, 61],
  ["nuclear", 95, 72],
  ["biomass", 88, 81],
  ["gas", 110, 96],
];

// GW: capacity already in place before the run vs what the optimiser added.
const CAPACITY_EXPANSION: [string, number, number][] = [
  ["solar-pv-utility", 210, 540],
  ["Onshore Wind", 230, 320],
  ["solar-pv-rooftop", 160, 290],
  ["offwind-dc", 30, 80],
  ["offwind-ac", 25, 125],
  ["H2 Electrolysis", 0, 240],
  ["Battery Storage", 10, 20],
  ["nuclear", 95, 0],
  ["gas", 180, 15],
];

interface BarSeries {
  name: string;
  color: string;
  values: number[];
}

// Narrow filters (one snapshot, one bus) leave totals well below 1.
function formatAmount(value: number) {
  return value !== 0 && Math.abs(value) < 1
    ? value.toLocaleString(undefined, { maximumSignificantDigits: 2 })
    : formatValue(value);
}

function CostBarChart({
  title,
  subtitle,
  categoryHeader,
  unit,
  categories,
  series,
  filteredBy,
  stacked = false,
  horizontal = false,
}: {
  title: string;
  subtitle: string;
  categoryHeader: string;
  unit: string;
  categories: string[];
  series: BarSeries[];
  filteredBy: FilterDimension[];
  stacked?: boolean;
  horizontal?: boolean;
}) {
  const colors = useChartColors();

  const option: EChartsOption = useMemo(() => {
    const categoryAxis = {
      type: "category" as const,
      data: categories,
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
        ? { left: 16, right: 24, top: 32, bottom: 40, containLabel: true }
        : { left: 64, right: 16, top: 32, bottom: 32 },
      legend: {
        right: 0,
        top: 4,
        data: series.map((item) => item.name),
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
          const lines = [
            `<div style="font-weight:600;margin-bottom:4px">${items[0].name}</div>`,
            ...items.map(
              (item) =>
                `${item.marker}${item.seriesName}: <b>${formatAmount(Number(item.value))}</b> ${unit}`,
            ),
          ];
          if (stacked)
            lines.push(
              `Total: <b>${formatAmount(items.reduce((sum, item) => sum + Number(item.value), 0))}</b> ${unit}`,
            );
          return lines.join("<br/>");
        },
      },
      xAxis: horizontal ? valueAxis : categoryAxis,
      yAxis: horizontal ? categoryAxis : valueAxis,
      series: series.map((item) => ({
        type: "bar" as const,
        name: item.name,
        stack: stacked ? "total" : undefined,
        data: item.values,
        itemStyle: { color: item.color },
        barMaxWidth: horizontal ? 18 : 64,
      })),
    };
  }, [colors, categories, series, stacked, horizontal, unit]);

  return (
    <WidgetCard
      title={title}
      subtitle={subtitle}
      filteredBy={filteredBy}
      data={categoryData(categoryHeader, categories, series, unit)}
    >
      {categories.length === 0 ? (
        <div className="text-surface-400 absolute inset-0 flex items-center justify-center text-[12px]">
          No data for the current filters.
        </div>
      ) : (
        <EChart option={option} />
      )}
    </WidgetCard>
  );
}

function costSeries(rows: [string, number, number][]): BarSeries[] {
  return [
    { name: "Capex", color: CAPEX_COLOR, values: rows.map(([, capex]) => capex) },
    { name: "Opex", color: OPEX_COLOR, values: rows.map(([, , opex]) => opex) },
  ];
}

// Annualised capex follows only the buses; opex is spent per hour, so it
// also follows the selected snapshots (with the carrier's seasonal shape).
function filterCostRows(
  rows: [string, number, number][],
  filters: InspectFilters,
  allBuses: string[],
  byCarrier: boolean,
  vary: Vary,
): [string, number, number][] {
  const share = busShare(filters, allBuses);
  return rows
    .filter(([label]) => !byCarrier || carrierAllowed(filters, label))
    .map(([label, capex, opex]) => [
      label,
      vary(`${label}|Capex`, capex) * share,
      vary(`${label}|Opex`, opex) * share * snapshotShare(filters, byCarrier ? label : undefined),
    ]);
}

const COMPONENT_FILTERED_BY: FilterDimension[] = ["bus", "snapshot"];
const CARRIER_FILTERED_BY: FilterDimension[] = ["bus", "snapshot", "carrier"];
const LCOE_FILTERED_BY: FilterDimension[] = ["snapshot", "carrier"];
const EXPANSION_FILTERED_BY: FilterDimension[] = ["bus", "carrier"];

export function CostByComponentChart({ resultName }: { resultName: string }) {
  const { filters, allBuses } = useInspectFilters();
  const vary = useResultVariation();
  const component = useMemo(() => {
    const rows = filterCostRows(COST_BY_COMPONENT, filters, allBuses, false, vary);
    return {
      categories: rows.map(([label]) => label),
      series: costSeries(rows),
      total: rows.reduce((sum, [, capex, opex]) => sum + capex + opex, 0),
    };
  }, [filters, allBuses, vary]);

  return (
    <CostBarChart
      title={`Annualised system cost by component: ${resultName}`}
      categoryHeader="Component"
      subtitle={`Capital and operational expenditure · total ${formatAmount(component.total)} bn €/a`}
      unit="bn €/a"
      categories={component.categories}
      series={component.series}
      filteredBy={COMPONENT_FILTERED_BY}
      stacked
    />
  );
}

export function CostByCarrierChart({ resultName }: { resultName: string }) {
  const { filters, allBuses } = useInspectFilters();
  const vary = useResultVariation();
  const carrier = useMemo(() => {
    const rows = filterCostRows(COST_BY_CARRIER, filters, allBuses, true, vary);
    return { categories: rows.map(([label]) => label), series: costSeries(rows) };
  }, [filters, allBuses, vary]);

  return (
    <CostBarChart
      title={`System cost by carrier: ${resultName}`}
      categoryHeader="Carrier"
      subtitle="Ten most expensive carriers, capex and opex"
      unit="bn €/a"
      categories={carrier.categories}
      series={carrier.series}
      filteredBy={CARRIER_FILTERED_BY}
      stacked
      horizontal
    />
  );
}

// Levelised cost is a fixed property of each carrier; market value tracks
// the price level in the selected snapshots.
export function LcoeVsMarketValueChart({ resultName }: { resultName: string }) {
  const { filters } = useInspectFilters();
  const vary = useResultVariation();
  const lcoe = useMemo(() => {
    const rows = LCOE_VS_MARKET_VALUE.filter(([label]) => carrierAllowed(filters, label));
    return {
      categories: rows.map(([label]) => label),
      series: [
        {
          name: "Levelised cost",
          color: CAPEX_COLOR,
          values: rows.map(
            ([label, levelisedCost]) => Math.round(vary(`${label}|lcoe`, levelisedCost) * 10) / 10,
          ),
        },
        {
          name: "Market value",
          color: OPEX_COLOR,
          values: rows.map(
            ([label, , marketValue]) =>
              Math.round(
                vary(`${label}|market value`, marketValue) * snapshotLevel(filters, label) * 10,
              ) / 10,
          ),
        },
      ],
    };
  }, [filters, vary]);

  return (
    <CostBarChart
      title={`Levelised cost vs market value: ${resultName}`}
      categoryHeader="Carrier"
      subtitle="Levelised cost of electricity against the average price each carrier earns"
      unit="€/MWh"
      categories={lcoe.categories}
      series={lcoe.series}
      filteredBy={LCOE_FILTERED_BY}
    />
  );
}

export function CapacityExpansionChart({ resultName }: { resultName: string }) {
  const { filters, allBuses } = useInspectFilters();
  const vary = useResultVariation();
  // What existed before the run is the same in every result; what it built isn't.
  const expansion = useMemo(() => {
    const share = busShare(filters, allBuses);
    const rows = CAPACITY_EXPANSION.filter(([label]) => carrierAllowed(filters, label));
    return {
      categories: rows.map(([label]) => label),
      series: [
        {
          name: "Existing",
          color: EXISTING_COLOR,
          values: rows.map(([, existing]) => existing * share),
        },
        {
          name: "Newly built",
          color: CAPEX_COLOR,
          values: rows.map(([label, , built]) => vary(`${label}|built`, built) * share),
        },
      ],
    };
  }, [filters, allBuses, vary]);

  return (
    <CostBarChart
      title={`Capacity expansion: ${resultName}`}
      categoryHeader="Carrier"
      subtitle="Existing capacity and what the optimisation added on top"
      unit="GW"
      categories={expansion.categories}
      series={expansion.series}
      filteredBy={EXPANSION_FILTERED_BY}
      stacked
    />
  );
}
