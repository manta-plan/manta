import type { ECharts } from "echarts";

// One value scale for the charts of a comparison: each chart reports the
// value-axis ranges echarts picked for its own data, and every chart in the
// group then shows the union, so equal heights mean equal values.

type Range = [number, number] | null;
interface AxisRanges {
  x: Range[];
  y: Range[];
}

interface ScaleGroup {
  natural: Map<string, AxisRanges>;
  charts: Map<string, ECharts>;
}

const groups = new Map<string, ScaleGroup>();

// echarts doesn't expose the extent it chose, so this reads its model.
function readRanges(chart: ECharts): AxisRanges {
  const model = (
    chart as unknown as {
      getModel: () => {
        findComponents: (query: {
          mainType: string;
        }) => { axis?: { type: string; scale: { getExtent: () => [number, number] } } }[];
      };
    }
  ).getModel();
  const read = (mainType: string) =>
    model.findComponents({ mainType }).map((component): Range => {
      const axis = component.axis;
      if (!axis || axis.type !== "value") return null;
      const [min, max] = axis.scale.getExtent();
      return Number.isFinite(min) && Number.isFinite(max) ? [min, max] : null;
    });
  return { x: read("xAxis"), y: read("yAxis") };
}

function union(ranges: Range[][], index: number): Range {
  const present = ranges
    .map((list) => list[index])
    .filter((range): range is [number, number] => range !== null && range !== undefined);
  if (present.length === 0) return null;
  return [Math.min(...present.map(([min]) => min)), Math.max(...present.map(([, max]) => max))];
}

function apply(group: ScaleGroup) {
  const all = [...group.natural.values()];
  const axes = (key: "x" | "y") =>
    Array.from({ length: Math.max(0, ...all.map((ranges) => ranges[key].length)) }, (_, index) =>
      union(
        all.map((ranges) => ranges[key]),
        index,
      ),
    );
  const x = axes("x");
  const y = axes("y");
  for (const chart of group.charts.values()) {
    if (chart.isDisposed()) continue;
    const own = (ranges: Range[], key: "x" | "y") =>
      ranges
        .slice(0, readCount(group, chart, key))
        .map((range) => (range ? { min: range[0], max: range[1] } : {}));
    const xAxis = own(x, "x");
    const yAxis = own(y, "y");
    chart.setOption({
      ...(xAxis.length > 0 ? { xAxis } : {}),
      ...(yAxis.length > 0 ? { yAxis } : {}),
    });
  }
}

// Only as many axes as the chart has, so a union never adds one.
function readCount(group: ScaleGroup, chart: ECharts, key: "x" | "y") {
  for (const [id, other] of group.charts)
    if (other === chart) return group.natural.get(id)?.[key].length ?? 0;
  return 0;
}

/** Call right after setOption with a fresh option: records its natural ranges and syncs the group. */
export function syncChartScale(groupId: string, chartId: string, chart: ECharts) {
  const group = groups.get(groupId) ?? { natural: new Map(), charts: new Map() };
  groups.set(groupId, group);
  group.charts.set(chartId, chart);
  group.natural.set(chartId, readRanges(chart));
  apply(group);
}

export function leaveChartScale(groupId: string, chartId: string) {
  const group = groups.get(groupId);
  if (!group) return;
  group.charts.delete(chartId);
  group.natural.delete(chartId);
  if (group.charts.size === 0) groups.delete(groupId);
  else apply(group);
}
