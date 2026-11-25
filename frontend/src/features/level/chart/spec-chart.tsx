// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useChartHeight } from "./use-chart-height";
import { useMemo } from "react";
import { format } from "echarts";
import type { EChartsOption, SeriesOption } from "echarts";
import { EChart } from "../../project/components/echart";
import { timeZoom, useChartColors } from "../../project/lib/use-widget-chart";
import { ACCENT, formatNumber, timeLabel, type ChartSpec } from "./spec";

// Paints a ChartSpec: time series on a time axis (stacked areas, or a
// distribution band), duration curves on a value axis, bars on categories.
// Axis names stay inside the plot (outerBoundsMode 'same' + 'all'); long
// series get a zoom slider; the tooltip lists up to 8 values.

const TOOLTIP_VALUES = 8;
const BAR_ZOOM_AT = 24;

type TooltipItem = {
  seriesName?: string;
  value?: unknown;
  color?: unknown;
  axisValue?: unknown;
  seriesId?: string;
};

const valueOf = (item: TooltipItem): number | null => {
  const value = Array.isArray(item.value) ? item.value[1] : item.value;
  return value === null || value === undefined || value === "" ? null : Number(value);
};

const swatch = (color: unknown) =>
  `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;background:${format.encodeHTML(typeof color === "string" ? color : ACCENT)}"></span>`;

export function SpecChart({
  spec,
  height,
  group,
}: {
  spec: ChartSpec;
  height: number;
  group?: string;
}) {
  const shownHeight = useChartHeight(height);
  const colors = useChartColors();

  const option = useMemo<EChartsOption>(() => {
    const axisLabel = { color: colors.text, fontSize: 10, hideOverlap: true };
    const yAxis = {
      type: "value" as const,
      name: spec.unit ? `[${spec.unit}]` : undefined,
      nameLocation: "middle" as const,
      nameGap: 44,
      nameTextStyle: { color: colors.text, fontSize: 11 },
      axisLabel: {
        color: colors.text,
        fontSize: 10,
        formatter: (value: number) => formatNumber(value),
      },
      splitLine: { lineStyle: { color: colors.splitLine } },
      scale: spec.kind !== "bar",
    };
    const showLegend =
      spec.series.length > 1 &&
      spec.series.length <= 24 &&
      !(spec.kind === "time" && spec.distribution);
    const tooltipBase = {
      backgroundColor: colors.tooltipBackground,
      borderColor: colors.axisLine,
      textStyle: { color: colors.strongText, fontSize: 11 },
      confine: true,
    };
    const listTooltip = (title: string, items: TooltipItem[], unit: string) => {
      const shown = items.filter((item) => !item.seriesId?.startsWith("band:"));
      const rows = shown
        .slice(0, TOOLTIP_VALUES)
        .map(
          (item) =>
            `<div>${swatch(item.color)}${format.encodeHTML(item.seriesName ?? "")}: <b>${formatNumber(valueOf(item))}</b> ${unit}</div>`,
        );
      if (shown.length > TOOLTIP_VALUES)
        rows.push(`<div style="opacity:.7">and ${shown.length - TOOLTIP_VALUES} more</div>`);
      return `<div style="font-weight:500;margin-bottom:2px">${title}</div>${rows.join("")}`;
    };
    const base: EChartsOption = {
      backgroundColor: "transparent",
      animation: false,
      // Snapshots are stored in UTC.
      useUTC: true,
      textStyle: { color: colors.text, fontSize: 11, fontFamily: "Inter, sans-serif" },
      legend: showLegend
        ? {
            type: "scroll",
            top: 0,
            left: 0,
            right: 0,
            textStyle: { color: colors.text, fontSize: 11 },
            pageTextStyle: { color: colors.text },
            itemWidth: 10,
            itemHeight: 10,
          }
        : undefined,
    };

    if (spec.kind === "time") {
      const zoom = timeZoom(colors, spec.times.length);
      const points = (values: (number | null)[]) =>
        spec.times.map((time, index) => [time, values[index] ?? null]);
      const series: SeriesOption[] = [];
      const distribution = spec.distribution;
      if (distribution) {
        // Bands as stacked areas: an invisible floor, then the band's height on top.
        const band = (id: string, low: number[], high: number[], opacity: number) => {
          series.push({
            id: `band:${id}:low`,
            type: "line",
            stack: id,
            data: points(low),
            symbol: "none",
            lineStyle: { opacity: 0 },
            silent: true,
          });
          series.push({
            id: `band:${id}:high`,
            type: "line",
            stack: id,
            data: points(high.map((value, index) => value - low[index])),
            symbol: "none",
            lineStyle: { opacity: 0 },
            areaStyle: { color: ACCENT, opacity },
            silent: true,
          });
        };
        band("range", distribution.min, distribution.max, 0.13);
        band("quartiles", distribution.p25, distribution.p75, 0.3);
        series.push({
          id: "median",
          name: `Median of ${distribution.count}`,
          type: "line",
          data: points(distribution.median),
          symbol: "none",
          lineStyle: { width: 2, color: ACCENT },
          itemStyle: { color: ACCENT },
        });
      }
      for (const item of spec.series) {
        series.push({
          name: item.name,
          type: "line",
          data: points(item.values),
          symbol: "none",
          sampling: spec.stacked ? undefined : "lttb",
          stack: spec.stacked ? "total" : undefined,
          lineStyle: { width: spec.stacked ? 0 : 1.5, color: item.color },
          areaStyle: spec.stacked ? { color: item.color, opacity: 0.85 } : undefined,
          itemStyle: { color: item.color },
        });
      }
      return {
        ...base,
        grid: {
          left: 8,
          right: 16,
          top: showLegend ? 32 : 12,
          bottom: zoom.gridBottom,
          outerBoundsMode: "same",
          outerBoundsContain: "all",
        },
        dataZoom: zoom.dataZoom,
        tooltip: {
          ...tooltipBase,
          trigger: "axis",
          formatter: (params: unknown) => {
            const items = (Array.isArray(params) ? params : [params]) as TooltipItem[];
            const first = items[0];
            const time = Array.isArray(first?.value)
              ? Number(first.value[0])
              : Number(first?.axisValue);
            if (distribution) {
              const index = spec.times.indexOf(time);
              const at = (values: number[]) => formatNumber(values[index]);
              return `<div style="font-weight:500;margin-bottom:2px">${timeLabel(time)}</div><div>Median <b>${at(distribution.median)}</b> ${spec.unit}</div><div>P25–P75 ${at(distribution.p25)} – ${at(distribution.p75)}</div><div>Min–max ${at(distribution.min)} – ${at(distribution.max)}</div>`;
            }
            return listTooltip(timeLabel(time), items, spec.unit);
          },
        },
        xAxis: {
          type: "time",
          axisLine: { lineStyle: { color: colors.axisLine } },
          axisTick: { show: false },
          axisLabel,
          splitLine: { show: false },
        },
        yAxis,
        series,
      };
    }

    if (spec.kind === "duration") {
      return {
        ...base,
        grid: {
          left: 8,
          right: 16,
          top: showLegend ? 32 : 12,
          bottom: 8,
          outerBoundsMode: "same",
          outerBoundsContain: "all",
        },
        tooltip: {
          ...tooltipBase,
          trigger: "axis",
          formatter: (params: unknown) => {
            const items = (Array.isArray(params) ? params : [params]) as TooltipItem[];
            const x = Array.isArray(items[0]?.value)
              ? Number(items[0].value[0])
              : Number(items[0]?.axisValue);
            return listTooltip(`${formatNumber(x)} ${spec.xName.toLowerCase()}`, items, spec.unit);
          },
        },
        xAxis: {
          type: "value",
          name: spec.xName,
          nameLocation: "middle",
          nameGap: 24,
          nameTextStyle: { color: colors.text, fontSize: 11 },
          min: 0,
          max: spec.x[spec.x.length - 1],
          axisLine: { lineStyle: { color: colors.axisLine } },
          axisLabel,
          splitLine: { show: false },
        },
        yAxis,
        series: spec.series.map((item) => ({
          name: item.name,
          type: "line",
          step: spec.xName === "Hours" ? "end" : undefined,
          data: spec.x.map((x, index) => [x, item.values[index] ?? null]),
          symbol: spec.x.length <= 40 ? "circle" : "none",
          symbolSize: 4,
          lineStyle: { width: 1.5, color: item.color },
          itemStyle: { color: item.color },
        })),
      };
    }

    const zoom = spec.categories.length > BAR_ZOOM_AT;
    return {
      ...base,
      grid: {
        left: 8,
        right: 16,
        top: showLegend ? 32 : 12,
        bottom: zoom ? 30 : 8,
        outerBoundsMode: "same",
        outerBoundsContain: "all",
      },
      dataZoom: zoom
        ? [
            {
              type: "inside",
              zoomOnMouseWheel: "ctrl",
              moveOnMouseWheel: false,
              moveOnMouseMove: true,
              startValue: 0,
              endValue: BAR_ZOOM_AT - 1,
            },
            {
              type: "slider",
              height: 14,
              bottom: 4,
              startValue: 0,
              endValue: BAR_ZOOM_AT - 1,
              borderColor: colors.axisLine,
              textStyle: { color: colors.text, fontSize: 10 },
              brushSelect: false,
              showDetail: false,
            },
          ]
        : undefined,
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: unknown) => {
          const items = ((Array.isArray(params) ? params : [params]) as TooltipItem[]).filter(
            (item) => (valueOf(item) ?? 0) !== 0,
          );
          return listTooltip(
            String((items[0] ?? (Array.isArray(params) ? params[0] : params))?.axisValue ?? ""),
            items.sort((a, b) => (valueOf(b) ?? 0) - (valueOf(a) ?? 0)),
            spec.unit,
          );
        },
      },
      xAxis: {
        type: "category",
        data: spec.categories,
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: colors.text,
          fontSize: 10,
          interval: 0,
          rotate: spec.categories.length > 6 ? 30 : 0,
          width: 110,
          overflow: "truncate",
        },
      },
      yAxis,
      series: spec.series.map((item) => ({
        name: item.name,
        type: "bar",
        stack: spec.stacked ? "total" : undefined,
        barMaxWidth: 36,
        itemStyle: { color: item.color },
        data: item.values.map((value, index) =>
          spec.barColors ? { value, itemStyle: { color: spec.barColors[index] } } : value,
        ),
      })),
    };
  }, [spec, colors]);

  return (
    <div style={{ height: shownHeight }} className="w-full min-w-0">
      <EChart key={spec.kind} option={option} group={group} className="h-full w-full" />
    </div>
  );
}
