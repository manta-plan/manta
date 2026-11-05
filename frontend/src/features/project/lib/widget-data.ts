// The table behind a widget, as the data drawer shows it. Headers carry
// units; time series are wide, one row per snapshot and a column per series.

export type WidgetDataCell = string | number | null;

export interface WidgetData {
  columns: string[];
  rows: WidgetDataCell[][];
}

/** Categories down the side, one column per series. */
export function categoryData(
  categoryHeader: string,
  categories: string[],
  series: { name: string; values: (number | null)[] }[],
  unit: string,
): WidgetData {
  return {
    columns: [categoryHeader, ...series.map((item) => `${item.name} [${unit}]`)],
    rows: categories.map((category, index) => [
      category,
      ...series.map((item) => item.values[index] ?? null),
    ]),
  };
}

/** Label/value pairs, the shape most single-series bar charts use. */
export function pairData(
  labelHeader: string,
  valueHeader: string,
  rows: [string, number][],
): WidgetData {
  return {
    columns: [labelHeader, valueHeader],
    rows: rows.map(([label, value]) => [label, value]),
  };
}

export function widgetDataCsv(data: WidgetData) {
  const escape = (cell: WidgetDataCell) => `"${String(cell ?? "").replaceAll('"', '""')}"`;
  return [data.columns, ...data.rows].map((row) => row.map(escape).join(",")).join("\n");
}
