import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { LuChartNoAxesCombined, LuPin, LuX } from "react-icons/lu";
import type { ResultCollection } from "../../project/data/result-collections";
import { useAppStore } from "../../home/store";
import { EChart } from "../../project/components/echart";
import { resultChartValueLabel, type ResultChartPoint } from "../lib/result-chart-data";

// Literal hex, not CSS vars — echarts paints to canvas (see ChartCard.tsx).
const BAR_COLOR = "#5699ff";
const PINNED_BAR_COLOR = "#8ec1ff";

function escapeHtml(text: string) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatValue(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

interface ResultChartProps {
  title: string;
  collection: ResultCollection;
  points: ResultChartPoint[];
  bounds: [number, number];
  comparison?: { title: string; points: ResultChartPoint[] };
  // Category label pinned across both compared charts — owned by the
  // parent so one click focuses the same category on each side.
  pinnedLabel: string | null;
  onPinnedLabelChange: (label: string | null) => void;
  // Links hover across the two charts of one comparison; each view needs its own.
  comparisonGroup: string;
}

export function ResultChart({
  title,
  collection,
  points,
  bounds,
  comparison,
  pinnedLabel,
  onPinnedLabelChange,
  comparisonGroup,
}: ResultChartProps) {
  const theme = useAppStore((s) => s.theme);
  const valueLabel = resultChartValueLabel(collection);
  const pinnedIndex =
    pinnedLabel === null ? -1 : points.findIndex((point) => point.label === pinnedLabel);

  const option: EChartsOption = useMemo(() => {
    const textColor = theme === "dark" ? "#a0b6ca" : "#475569";
    const axisLineColor = theme === "dark" ? "#2c4763" : "#cbd5e1";
    const splitLineColor = theme === "dark" ? "#16253a" : "#f1f5f9";
    const tooltipBackground = theme === "dark" ? "#0b1522" : "#ffffff";
    const strongTextColor = theme === "dark" ? "#e6eef6" : "#0f172a";

    return {
      backgroundColor: "transparent",
      textStyle: { color: textColor, fontSize: 11, fontFamily: "Inter, sans-serif" },
      grid: { left: 56, right: 16, top: 28, bottom: 48 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: tooltipBackground,
        borderColor: axisLineColor,
        textStyle: { color: strongTextColor, fontSize: 11 },
        // Shows this run's value against the compared run's for the same
        // category — with the charts connected, both tooltips open together.
        formatter: (params) => {
          const dataIndex = (Array.isArray(params) ? params[0] : params).dataIndex;
          const point = points[dataIndex];
          if (!point) return "";
          const lines = [
            `<div style="font-weight:600;margin-bottom:4px">${escapeHtml(point.label)}</div>`,
            `${escapeHtml(title)}: <b>${formatValue(point.value)}</b>`,
          ];
          const comparisonPoint = comparison?.points[dataIndex];
          if (comparison && comparisonPoint) {
            const delta = point.value - comparisonPoint.value;
            const percent =
              comparisonPoint.value !== 0 ? (delta / Math.abs(comparisonPoint.value)) * 100 : null;
            const deltaColor = delta > 0 ? "#22c55e" : delta < 0 ? "#ef4444" : textColor;
            lines.push(`${escapeHtml(comparison.title)}: ${formatValue(comparisonPoint.value)}`);
            lines.push(
              `<span style="color:${deltaColor}">Δ ${delta > 0 ? "+" : ""}${formatValue(delta)}${percent === null ? "" : ` (${percent > 0 ? "+" : ""}${percent.toFixed(1)}%)`}</span>`,
            );
          }
          return lines.join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: points.map((point) => point.label),
        axisLine: { lineStyle: { color: axisLineColor } },
        axisTick: { show: false },
        axisLabel: { color: textColor, fontSize: 10, interval: 0, width: 72, overflow: "break" },
      },
      yAxis: {
        type: "value",
        name: valueLabel,
        nameTextStyle: { color: textColor, fontSize: 10, align: "left" },
        min: bounds[0],
        max: bounds[1],
        axisLabel: { color: textColor, fontSize: 10 },
        splitLine: { lineStyle: { color: splitLineColor } },
      },
      series: [
        {
          type: "bar",
          // Per-item style so a pin can fade every other category.
          data: points.map((point, index) => {
            const isFaded = pinnedIndex >= 0 && index !== pinnedIndex;
            return {
              value: point.value,
              itemStyle: {
                color: index === pinnedIndex ? PINNED_BAR_COLOR : BAR_COLOR,
                opacity: isFaded ? 0.25 : 1,
              },
              label: {
                color: index === pinnedIndex ? strongTextColor : textColor,
                fontWeight: index === pinnedIndex ? 600 : 400,
                opacity: isFaded ? 0.4 : 1,
              },
            };
          }),
          itemStyle: { borderRadius: [2, 2, 0, 0] },
          emphasis: { itemStyle: { color: PINNED_BAR_COLOR } },
          barMaxWidth: 40,
          cursor: "pointer",
          label: {
            show: true,
            position: "top",
            fontSize: 10,
            formatter: ({ value }) => formatValue(Number(value)),
          },
        },
      ],
    };
  }, [theme, points, bounds, comparison, title, valueLabel, pinnedIndex]);

  return (
    <section className="border-surface-700 bg-surface-900 flex min-h-0 min-w-0 flex-1 flex-col border p-4">
      <div className="border-surface-700 flex h-10 shrink-0 items-start justify-between border-b pb-2">
        <div className="min-w-0">
          <div className="text-surface-100 truncate text-[12px] font-medium">{title}</div>
          <div className="text-surface-400 truncate text-[11px]">
            {collection.label} trend preview
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {pinnedIndex >= 0 ? (
            <button
              type="button"
              onClick={() => onPinnedLabelChange(null)}
              title="Clear pin"
              className="border-accent-500/60 bg-accent-600/15 text-accent-400 hover:bg-accent-600/25 flex h-6 max-w-40 shrink-0 items-center gap-1 rounded border px-1.5 text-[11px] font-medium outline-none"
            >
              <LuPin size={11} className="shrink-0" />
              <span className="truncate">{points[pinnedIndex].label}</span>
              <LuX size={11} className="shrink-0" />
            </button>
          ) : (
            <LuChartNoAxesCombined size={15} className="text-accent-400 shrink-0" />
          )}
        </div>
      </div>
      <EChart
        option={option}
        group={comparison ? comparisonGroup : undefined}
        // Anywhere in a category's column toggles its pin; outside the plot clears it.
        onCanvasClick={(chart, point) => {
          if (!chart.containPixel("grid", point)) {
            onPinnedLabelChange(null);
            return;
          }
          const [index] = chart.convertFromPixel({ seriesIndex: 0 }, point) as number[];
          const label = points[Math.round(index)]?.label ?? null;
          onPinnedLabelChange(label === pinnedLabel ? null : label);
        }}
        className="min-h-0 flex-1"
      />
    </section>
  );
}
