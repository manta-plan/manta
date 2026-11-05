import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import {
  busShare,
  carrierAllowed,
  describeSnapshots,
  snapshotLabel,
  snapshotRange,
  snapshotShare,
  useInspectFilters,
  type SnapshotFilter,
} from "../../project/lib/inspect-filters";
import {
  BAR_COLOR,
  CARRIER_COLORS,
  formatValue,
  useChartColors,
} from "../../project/lib/use-widget-chart";
import { categoryData, type WidgetData } from "../../project/lib/widget-data";
import { EChart } from "../../project/components/echart";
import { WidgetCard } from "./widget-card";
import { CURTAILMENT } from "../../project/data/inspect-dummy-data";
import { STACK_ORDER, round, simulate } from "../../project/lib/dispatch-simulation";
import { useResultVariation } from "../../project/lib/result-comparison";

// The "Power Dispatch" built-in inspection: how the system runs hour by hour over the
// snapshots the page's filters pick on a dummy 2040 hourly year. Values are
// generated placeholders, not solver output.

// 16 Jan 2040: the week shown when no snapshot filter is set.
const REPRESENTATIVE_START = 15 * 24;
// Longer windows switch to daily averages so the charts stay light.
const HOURLY_LIMIT = 21 * 24;

interface DispatchWindow {
  start: number;
  end: number;
  daily: boolean;
  /** The single snapshot to mark, if one is picked. */
  markHour: number | null;
  description: string;
}

function dispatchWindow(snapshots: SnapshotFilter): DispatchWindow {
  if (snapshots.mode === "all")
    return {
      start: REPRESENTATIVE_START,
      end: REPRESENTATIVE_START + 167,
      daily: false,
      markHour: null,
      description: "Representative week (16–22 Jan), hourly",
    };
  if (snapshots.mode === "single") {
    const start = snapshots.hour - (snapshots.hour % 24);
    return {
      start,
      end: start + 23,
      daily: false,
      markHour: snapshots.hour,
      description: `The day of ${snapshotLabel(snapshots.hour)}, hourly`,
    };
  }
  const [start, end] = snapshotRange(snapshots);
  const daily = end - start + 1 > HOURLY_LIMIT;
  return {
    start,
    end,
    daily,
    markHour: null,
    description: `${describeSnapshots(snapshots)}, ${daily ? "daily averages" : "hourly"}`,
  };
}

function dailyAverages(values: number[]) {
  const days: number[] = [];
  for (let index = 0; index < values.length; index += 24) {
    const chunk = values.slice(index, index + 24);
    days.push(round(chunk.reduce((sum, value) => sum + value, 0) / chunk.length));
  }
  return days;
}

interface DispatchSeries {
  window: DispatchWindow;
  labels: string[];
  /** Category label of the marked snapshot, for a markLine. */
  markLabel: string | null;
  carriers: Record<string, number[]>;
  load: number[];
  storage: Record<string, number[]>;
  /** Hourly prices of the window, never averaged. */
  prices: number[];
}

// Each widget reads the same window, so it's simulated once per filter.
const seriesCache = new Map<string, DispatchSeries>();

function dispatchSeries(snapshots: SnapshotFilter): DispatchSeries {
  const window = dispatchWindow(snapshots);
  const key = `${window.start}-${window.end}-${window.markHour}`;
  const cached = seriesCache.get(key);
  if (cached) return cached;
  const simulation = simulate(window.start, window.end);
  const shape = window.daily ? dailyAverages : (values: number[]) => values;
  const hours = Array.from(
    { length: window.end - window.start + 1 },
    (_, index) => window.start + index,
  );
  const labels = window.daily
    ? hours.filter((_, index) => index % 24 === 0).map((hour) => snapshotLabel(hour).slice(0, -6))
    : hours.map(snapshotLabel);
  const series: DispatchSeries = {
    window,
    labels,
    markLabel: window.markHour === null ? null : snapshotLabel(window.markHour),
    carriers: Object.fromEntries(
      Object.entries(simulation.carriers).map(([carrier, values]) => [carrier, shape(values)]),
    ),
    load: shape(simulation.load),
    storage: Object.fromEntries(
      Object.entries(simulation.storage).map(([name, values]) => [name, shape(values)]),
    ),
    prices: simulation.prices,
  };
  if (seriesCache.size > 20) seriesCache.clear();
  seriesCache.set(key, series);
  return series;
}

// The window's series for the result being drawn: each carrier, store and
// the price shift a little per result (see useResultVariation).
function useDispatchSeries(snapshots: SnapshotFilter): DispatchSeries {
  const vary = useResultVariation();
  const series = dispatchSeries(snapshots);
  return useMemo(() => {
    const scale = (key: string, values: number[], limit = Infinity) =>
      values.map((value) => round(Math.min(limit, vary(key, value))));
    return {
      ...series,
      carriers: Object.fromEntries(
        Object.entries(series.carriers).map(([carrier, values]) => [
          carrier,
          scale(carrier, values),
        ]),
      ),
      load: scale("load", series.load),
      storage: Object.fromEntries(
        Object.entries(series.storage).map(([name, values]) => [
          name,
          scale(`${name}|soc`, values, 100),
        ]),
      ),
      prices: scale("price", series.prices),
    };
  }, [series, vary]);
}

function NoData() {
  return (
    <div className="text-surface-400 absolute inset-0 flex items-center justify-center text-[12px]">
      No data for the current filters.
    </div>
  );
}

function timeAxis(series: DispatchSeries, colors: ReturnType<typeof useChartColors>) {
  return {
    type: "category" as const,
    boundaryGap: false,
    data: series.labels,
    axisLine: { lineStyle: { color: colors.axisLine } },
    axisTick: { show: false },
    axisLabel: series.window.daily
      ? { color: colors.text, fontSize: 10 }
      : // Hourly: one label per day, at midnight, without the time.
        {
          color: colors.text,
          fontSize: 10,
          interval: (index: number) => (series.window.start + index) % 24 === 0,
          formatter: (label: string) => label.slice(0, -6),
        },
  };
}

function markLine(series: DispatchSeries, colors: ReturnType<typeof useChartColors>) {
  return series.markLabel
    ? {
        symbol: "none",
        silent: true,
        data: [{ xAxis: series.markLabel }],
        lineStyle: { color: colors.strongText, type: "solid" as const, width: 1 },
        label: { formatter: series.markLabel, color: colors.strongText, fontSize: 10 },
      }
    : undefined;
}

export function DispatchStackChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters, allBuses } = useInspectFilters();
  const series = useDispatchSeries(filters.snapshots);

  const option: EChartsOption = useMemo(() => {
    const share = busShare(filters, allBuses);
    const scale = (values: number[]) => values.map((value) => round(value * share));
    const carriers = STACK_ORDER.filter((carrier) => carrierAllowed(filters, carrier));
    return {
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 64, right: 16, top: 36, bottom: 32 },
      legend: {
        type: "scroll",
        right: 0,
        left: 64,
        top: 4,
        textStyle: { color: colors.text, fontSize: 11 },
        pageTextStyle: { color: colors.text },
        itemWidth: 10,
        itemHeight: 10,
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        valueFormatter: (value) => `${formatValue(Number(value))} GW`,
      },
      xAxis: timeAxis(series, colors),
      yAxis: {
        type: "value",
        name: "Power [GW]",
        nameLocation: "middle",
        nameGap: 48,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: [
        // Generation stacks up from zero; battery charging and electrolysis stack below it.
        ...carriers.map((carrier) => ({
          type: "line" as const,
          name: carrier,
          stack: "dispatch",
          data: scale(series.carriers[carrier]),
          symbol: "none",
          lineStyle: { width: 0 },
          areaStyle: { color: CARRIER_COLORS[carrier] ?? BAR_COLOR, opacity: 0.9 },
          itemStyle: { color: CARRIER_COLORS[carrier] ?? BAR_COLOR },
        })),
        {
          type: "line" as const,
          name: "Load",
          data: scale(series.load),
          symbol: "none",
          lineStyle: { color: colors.strongText, width: 1.5, type: "dashed" as const },
          itemStyle: { color: colors.strongText },
          z: 10,
          markLine: markLine(series, colors),
        },
      ],
    };
  }, [colors, series, filters, allBuses]);

  // Wide, like a PyPSA dataframe: a row per snapshot (or day), a column per carrier.
  const data = useMemo(() => {
    const share = busShare(filters, allBuses);
    const scale = (values: number[]) => values.map((value) => round(value * share));
    const carriers = STACK_ORDER.filter((carrier) => carrierAllowed(filters, carrier));
    return categoryData(
      series.window.daily ? "Day" : "Snapshot",
      series.labels,
      [
        ...carriers.map((carrier) => ({ name: carrier, values: scale(series.carriers[carrier]) })),
        { name: "Load", values: scale(series.load) },
      ],
      "GW",
    );
  }, [series, filters, allBuses]);

  return (
    <WidgetCard
      title={`Dispatch by carrier: ${resultName}`}
      subtitle={`${series.window.description} · charging and electrolysis shown below zero`}
      filteredBy={["snapshot", "bus", "carrier"]}
      data={data}
    >
      <EChart option={option} />
    </WidgetCard>
  );
}

export function StorageSocChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters } = useInspectFilters();
  const series = useDispatchSeries(filters.snapshots);
  const stores = Object.keys(series.storage).filter((name) => carrierAllowed(filters, name));

  const option: EChartsOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 64, right: 16, top: 36, bottom: 32 },
      legend: {
        right: 0,
        top: 4,
        textStyle: { color: colors.text, fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        valueFormatter: (value) => `${formatValue(Number(value))}%`,
      },
      xAxis: timeAxis(series, colors),
      yAxis: {
        type: "value",
        name: "State of charge [%]",
        nameLocation: "middle",
        nameGap: 48,
        min: 0,
        max: 100,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: stores.map((name, index) => ({
        type: "line" as const,
        name,
        data: series.storage[name],
        symbol: "none",
        lineStyle: { width: 1.5, color: CARRIER_COLORS[name] ?? BAR_COLOR },
        itemStyle: { color: CARRIER_COLORS[name] ?? BAR_COLOR },
        markLine: index === 0 ? markLine(series, colors) : undefined,
      })),
    }),
    // `stores` is derived from these.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [colors, series, filters],
  );

  return (
    <WidgetCard
      title={`Storage state of charge: ${resultName}`}
      subtitle={`Share of each store's energy capacity · ${series.window.description}`}
      filteredBy={["snapshot", "carrier"]}
      data={categoryData(
        series.window.daily ? "Day" : "Snapshot",
        series.labels,
        stores.map((name) => ({ name, values: series.storage[name] })),
        "%",
      )}
    >
      {stores.length > 0 ? <EChart option={option} /> : <NoData />}
    </WidgetCard>
  );
}

export function CurtailmentChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters, allBuses } = useInspectFilters();
  const isWholeYear = filters.snapshots.mode === "all";
  // A slice of the year curtails far less than a TWh, so it reads in GWh.
  const unit = isWholeYear ? "TWh" : "GWh";

  const vary = useResultVariation();
  const rows = useMemo(() => {
    const share = busShare(filters, allBuses);
    return CURTAILMENT.filter(([carrier]) => carrierAllowed(filters, carrier)).map(
      ([carrier, energy, percent]) => {
        const value =
          vary(carrier, energy) *
          share *
          snapshotShare(filters, carrier) *
          (isWholeYear ? 1 : 1000);
        return { carrier, value: round(value), percent };
      },
    );
  }, [filters, allBuses, isWholeYear, vary]);

  const option: EChartsOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 64, right: 16, top: 24, bottom: 32 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params;
          const row = rows[item.dataIndex];
          return `${item.name}<br/><b>${formatValue(row.value)} ${unit}</b> · ${formatValue(row.percent)}% of available`;
        },
      },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.carrier),
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: colors.text, fontSize: 10, interval: 0 },
      },
      yAxis: {
        type: "value",
        name: `Curtailment [${unit}]`,
        nameLocation: "middle",
        nameGap: 48,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: [
        {
          type: "bar",
          data: rows.map((row) => ({
            value: row.value,
            itemStyle: { color: CARRIER_COLORS[row.carrier] ?? BAR_COLOR },
          })),
          barMaxWidth: 64,
          label: {
            show: true,
            position: "top",
            color: colors.text,
            fontSize: 10,
            formatter: ({ dataIndex }) => `${formatValue(rows[dataIndex].percent)}%`,
          },
        },
      ],
    }),
    [colors, rows, unit],
  );

  return (
    <WidgetCard
      title={`Curtailment by carrier: ${resultName}`}
      subtitle={`Energy curtailed ${isWholeYear ? "over the year" : `in ${describeSnapshots(filters.snapshots)}`} · labels show the share of available energy`}
      filteredBy={["snapshot", "bus", "carrier"]}
      data={{
        columns: ["Carrier", `Curtailed [${unit}]`, "Share of available energy [%]"],
        rows: rows.map((row) => [row.carrier, row.value, row.percent]),
      }}
    >
      {rows.length > 0 ? <EChart option={option} /> : <NoData />}
    </WidgetCard>
  );
}

// Prices stay hourly even when the window is shown as daily averages; sort
// the price column to get the duration curve.
function hourlyPriceData(series: DispatchSeries): WidgetData {
  return categoryData(
    "Snapshot",
    series.prices.map((_, index) => snapshotLabel(series.window.start + index)),
    [{ name: "Price", values: series.prices }],
    "€/MWh",
  );
}

export function PriceDurationChart({ resultName }: { resultName: string }) {
  const colors = useChartColors();
  const { filters } = useInspectFilters();
  const series = useDispatchSeries(filters.snapshots);

  const option: EChartsOption = useMemo(() => {
    const sorted = [...series.prices].sort((a, b) => b - a);
    const points = sorted.map((price, index) => [
      round((index / Math.max(1, sorted.length - 1)) * 100),
      price,
    ]);
    return {
      backgroundColor: "transparent",
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 64, right: 16, top: 24, bottom: 40 },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.tooltipBackground,
        borderColor: colors.axisLine,
        textStyle: { color: colors.strongText, fontSize: 11 },
        formatter: (params) => {
          const item = Array.isArray(params) ? params[0] : params;
          const [share, price] = item.value as number[];
          return `${formatValue(share)}% of hours<br/>at or above <b>${formatValue(price)} €/MWh</b>`;
        },
      },
      xAxis: {
        type: "value",
        name: "Share of hours [%]",
        nameLocation: "middle",
        nameGap: 28,
        min: 0,
        max: 100,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        name: "Price [€/MWh]",
        nameLocation: "middle",
        nameGap: 48,
        nameTextStyle: { color: colors.text, fontSize: 11 },
        axisLabel: { color: colors.text, fontSize: 10 },
        splitLine: { lineStyle: { color: colors.splitLine } },
      },
      series: [
        {
          type: "line",
          data: points,
          symbol: "none",
          lineStyle: { color: BAR_COLOR, width: 2 },
          areaStyle: { color: BAR_COLOR, opacity: 0.15 },
        },
      ],
    };
  }, [colors, series]);

  return (
    <WidgetCard
      title={`Price duration curve: ${resultName}`}
      subtitle={`Hourly electricity prices sorted high to low · ${series.window.description.replace(/, (hourly|daily averages)$/, "")}`}
      filteredBy={["snapshot"]}
      data={hourlyPriceData(series)}
    >
      <EChart option={option} />
    </WidgetCard>
  );
}
