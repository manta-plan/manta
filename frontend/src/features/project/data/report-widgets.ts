// Dummy pre-configured report widgets — stands in for a future
// "add/configure widget" builder wired to real run output. Each Report owns
// its own widgets array (see Report.widgets in reports.ts); these arrays are
// just the starter sets the New Report canvas presets populate.

export interface StatWidget {
  id: string;
  widgetType: "stat";
  label: string;
  value: string;
  sublabel: string;
  trend?: { direction: "up" | "down"; value: string };
}

export type ChartKind = "pie" | "line" | "bar";

export type ChartWidget =
  | {
      id: string;
      widgetType: "chart";
      title: string;
      kind: "pie";
      data: { name: string; value: number }[];
    }
  | {
      id: string;
      widgetType: "chart";
      title: string;
      kind: "line";
      categories: string[];
      series: { name: string; data: number[] }[];
    }
  | {
      id: string;
      widgetType: "chart";
      title: string;
      kind: "bar";
      categories: string[];
      series: { name: string; data: number[] }[];
    };

export type ReportWidget = StatWidget | ChartWidget;

export const CHART_WIDGETS: ChartWidget[] = [
  {
    id: "chart-capacity-mix",
    widgetType: "chart",
    title: "Capacity Mix by Carrier",
    kind: "pie",
    data: [
      { name: "Wind", value: 38 },
      { name: "Gas", value: 24 },
      { name: "Solar", value: 14 },
      { name: "Nuclear", value: 12 },
      { name: "Battery", value: 7 },
      { name: "Coal", value: 5 },
    ],
  },
  {
    id: "chart-generation-by-month",
    widgetType: "chart",
    title: "Generation by Month",
    kind: "line",
    categories: [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ],
    series: [
      { name: "Wind", data: [420, 390, 350, 300, 260, 220, 210, 230, 280, 340, 400, 440] },
      { name: "Gas", data: [280, 260, 230, 190, 150, 120, 110, 130, 170, 210, 250, 290] },
      { name: "Solar", data: [40, 60, 100, 150, 200, 230, 240, 210, 160, 100, 50, 30] },
    ],
  },
  {
    id: "chart-cost-breakdown",
    widgetType: "chart",
    title: "Cost Breakdown",
    kind: "bar",
    categories: ["Capex", "Opex", "Fuel", "Emissions"],
    series: [{ name: "Cost (£M)", data: [820, 540, 610, 210] }],
  },
];

// The "Use output summary" canvas preset: a complete results dashboard —
// headline metrics across cost, supply, emissions and reliability, then
// charts covering capacity, generation, cost, emissions, storage and grid.
// Still sample data (no run-output pipeline yet), shaped like a real solve.
export const OUTPUT_SUMMARY_STATS: StatWidget[] = [
  {
    id: "stat-system-cost",
    widgetType: "stat",
    label: "System Cost",
    value: "£2.18B",
    sublabel: "total annualised",
    trend: { direction: "down", value: "4.1%" },
  },
  {
    id: "stat-renewable-share",
    widgetType: "stat",
    label: "Renewable Share",
    value: "62%",
    sublabel: "of total generation",
    trend: { direction: "up", value: "8.3%" },
  },
  {
    id: "stat-emissions",
    widgetType: "stat",
    label: "CO₂ Emissions",
    value: "1.24 Mt",
    sublabel: "annual total",
    trend: { direction: "down", value: "12.6%" },
  },
  {
    id: "stat-peak-demand",
    widgetType: "stat",
    label: "Peak Demand",
    value: "48.2 GW",
    sublabel: "winter peak",
  },
  {
    id: "stat-total-generation",
    widgetType: "stat",
    label: "Total Generation",
    value: "312 TWh",
    sublabel: "annual output",
    trend: { direction: "up", value: "2.4%" },
  },
  {
    id: "stat-avg-price",
    widgetType: "stat",
    label: "Avg. Wholesale Price",
    value: "£54/MWh",
    sublabel: "load-weighted",
    trend: { direction: "down", value: "3.2%" },
  },
  {
    id: "stat-curtailment",
    widgetType: "stat",
    label: "Curtailment",
    value: "2.1%",
    sublabel: "of renewable output",
    trend: { direction: "down", value: "0.4%" },
  },
  {
    id: "stat-unserved-energy",
    widgetType: "stat",
    label: "Unserved Energy",
    value: "0 MWh",
    sublabel: "no load shedding",
  },
];

export const OUTPUT_SUMMARY_CHARTS: ChartWidget[] = [
  CHART_WIDGETS[0],
  {
    id: "chart-generation-share",
    widgetType: "chart",
    title: "Generation Share by Carrier",
    kind: "pie",
    data: [
      { name: "Wind", value: 41 },
      { name: "Gas", value: 21 },
      { name: "Nuclear", value: 18 },
      { name: "Solar", value: 13 },
      { name: "Hydro", value: 4 },
      { name: "Imports", value: 3 },
    ],
  },
  {
    id: "chart-capacity-expansion",
    widgetType: "chart",
    title: "Installed Capacity — Existing vs Optimised (GW)",
    kind: "bar",
    categories: ["Wind", "Solar", "Gas", "Nuclear", "Battery"],
    series: [
      { name: "Existing", data: [12, 8, 15, 6, 1] },
      { name: "Optimised", data: [18, 14, 11, 6, 4] },
    ],
  },
  CHART_WIDGETS[1],
  CHART_WIDGETS[2],
  {
    id: "chart-emissions-by-month",
    widgetType: "chart",
    title: "CO₂ Emissions by Month (kt)",
    kind: "line",
    categories: [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ],
    series: [{ name: "CO₂", data: [140, 128, 112, 95, 80, 70, 66, 72, 88, 104, 122, 138] }],
  },
  {
    id: "chart-battery-soc",
    widgetType: "chart",
    title: "Battery State of Charge — Typical Winter Day (GWh)",
    kind: "line",
    categories: ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"],
    series: [{ name: "State of charge", data: [2.1, 3.4, 3.8, 2.2, 1.4, 2.6, 1.2, 0.9] }],
  },
  {
    id: "chart-line-loading",
    widgetType: "chart",
    title: "Most Loaded Transmission Lines (avg. %)",
    kind: "bar",
    categories: ["BE–NL North", "BE–FR West", "Brussels Ring", "Antwerp–Ghent", "Liège–Namur"],
    series: [{ name: "Avg. loading (%)", data: [86, 79, 72, 68, 61] }],
  },
];

// One canned dataset per chart kind — the widget config form lets a user
// choose a chart type, not hand-edit series data (no real data pipeline
// behind these yet), so picking a kind picks its matching sample dataset.
// Every ChartKind is guaranteed a match since CHART_WIDGETS seeds one of each.
export function chartPresetForKind(kind: ChartKind): ChartWidget {
  return CHART_WIDGETS.find((widget) => widget.kind === kind)!;
}
