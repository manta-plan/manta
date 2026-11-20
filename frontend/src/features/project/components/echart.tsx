import { useEffect, useId, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { leaveChartScale, syncChartScale } from "../lib/chart-scale-sync";
import { useComparison } from "../lib/result-comparison";

// Thin imperative wrapper (init/setOption/resize/dispose) rather than a
// dependency like echarts-for-react — mirrors how MapView drives maplibre
// directly via refs, so the two "external viz library in a React shell"
// integrations in this app follow the same pattern.
// `group` links every chart sharing it via echarts.connect, so hover
// (tooltip/axis pointer), legend toggles and data zoom stay in sync.
// `onCanvasClick` fires for any click on the canvas (not just on a series
// item) with the chart and pixel point, so callers can resolve it against
// the grid themselves — e.g. a click anywhere in a category's column.
// Inside a compared widget, both results' charts share hover and value scale.
export function EChart({
  option,
  className,
  group: groupProp,
  onCanvasClick,
}: {
  option: EChartsOption;
  className?: string;
  group?: string;
  onCanvasClick?: (chart: echarts.ECharts, point: [number, number]) => void;
}) {
  const chartId = useId();
  const scaleGroup = useComparison()?.chartGroup;
  const group = groupProp ?? scaleGroup;
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const onCanvasClickRef = useRef(onCanvasClick);
  useEffect(() => {
    onCanvasClickRef.current = onCanvasClick;
  }, [onCanvasClick]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = echarts.init(container);
    chartRef.current = chart;
    chart
      .getZr()
      .on("click", (event) => onCanvasClickRef.current?.(chart, [event.offsetX, event.offsetY]));
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !group) return;
    chart.group = group;
    echarts.connect(group);
    return () => {
      chart.group = "";
    };
  }, [group]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.setOption(option, true);
    if (scaleGroup) syncChartScale(scaleGroup, chartId, chart);
  }, [option, scaleGroup, chartId]);

  useEffect(() => {
    if (!scaleGroup) return;
    return () => leaveChartScale(scaleGroup, chartId);
  }, [scaleGroup, chartId]);

  return <div ref={containerRef} className={className ?? "h-full w-full"} />;
}
