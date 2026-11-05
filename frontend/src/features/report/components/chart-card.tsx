import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChart } from "../../project/components/echart";
import { useProjectStore } from "../../project/store/project-store";
import { useAppStore } from "../../home/store";
import type { ChartWidget } from "../../project/data/report-widgets";

// Brand-derived series palette, semantically ordered to match the dummy
// data (Wind/blue, Gas/amber, Solar/lime, ...) — kept as literal hex since
// echarts paints to canvas and can't resolve CSS custom properties itself,
// same reasoning MapView already follows for maplibre's paint properties.
const SERIES_COLORS = ["#5699ff", "#d9a521", "#61c568", "#3a9c92", "#8ec1ff", "#6ebcb2"];

export function ChartCard({ widget }: { widget: ChartWidget }) {
  const theme = useAppStore((s) => s.theme);
  const openWidgetConfigDrawer = useProjectStore((s) => s.openWidgetConfigDrawer);

  const option: EChartsOption = useMemo(() => {
    const textColor = theme === "dark" ? "#a0b6ca" : "#475569";
    const axisLineColor = theme === "dark" ? "#2c4763" : "#cbd5e1";
    const splitLineColor = theme === "dark" ? "#16253a" : "#f1f5f9";
    const textStyle = { color: textColor, fontSize: 11, fontFamily: "Inter, sans-serif" };

    if (widget.kind === "pie") {
      return {
        backgroundColor: "transparent",
        color: SERIES_COLORS,
        textStyle,
        tooltip: { trigger: "item" },
        legend: { bottom: 0, textStyle, itemWidth: 10, itemHeight: 10 },
        series: [
          {
            type: "pie",
            radius: ["40%", "70%"],
            center: ["50%", "44%"],
            itemStyle: { borderColor: "transparent", borderWidth: 2 },
            label: { color: textColor, fontSize: 11 },
            data: widget.data,
          },
        ],
      };
    }

    const isMultiSeries = widget.series.length > 1;
    const shared: EChartsOption = {
      backgroundColor: "transparent",
      color: SERIES_COLORS,
      textStyle,
      tooltip: { trigger: "axis" },
      legend: isMultiSeries ? { top: 0, textStyle, itemWidth: 10, itemHeight: 10 } : undefined,
      grid: { left: 36, right: 12, top: isMultiSeries ? 28 : 12, bottom: 24 },
      xAxis: {
        type: "category",
        data: widget.categories,
        axisLine: { lineStyle: { color: axisLineColor } },
        axisLabel: { color: textColor, fontSize: 11 },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: { lineStyle: { color: axisLineColor } },
        axisLabel: { color: textColor, fontSize: 11 },
        splitLine: { lineStyle: { color: splitLineColor } },
      },
    };

    if (widget.kind === "line") {
      return {
        ...shared,
        series: widget.series.map((s) => ({
          name: s.name,
          type: "line" as const,
          data: s.data,
          smooth: true,
          showSymbol: false,
        })),
      };
    }

    return {
      ...shared,
      series: widget.series.map((s) => ({ name: s.name, type: "bar" as const, data: s.data })),
    };
  }, [widget, theme]);

  return (
    <div
      onClick={() => openWidgetConfigDrawer(widget.id)}
      className="border-surface-700 bg-surface-800 hover:border-accent-500/60 flex h-80 cursor-pointer flex-col gap-2 rounded-lg border p-3 outline-none"
    >
      <div className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">
        {widget.title}
      </div>
      <EChart option={option} className="min-h-0 flex-1" />
    </div>
  );
}
