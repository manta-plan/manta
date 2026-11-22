import {
  CHART_WIDGETS,
  OUTPUT_SUMMARY_CHARTS,
  OUTPUT_SUMMARY_STATS,
  type ReportWidget,
} from "./report-widgets";

export type ReportCanvasPreset = "blank" | "playbook-hint" | "output-summary";

export interface Report {
  id: string;
  name: string;
  scenarioName: string;
  generatedAt: string;
  // ReportDashboard shows a blank-canvas state when this is empty (new
  // reports created via the "New Report" drawer start this way) instead of
  // the widget grid.
  widgets: ReportWidget[];
  // The specific scenario result (succeeded Run) a report was generated
  // from — only set for reports created via the New Report drawer, which
  // now picks a result rather than a bare scenario.
  runId?: string;
  canvasPreset?: ReportCanvasPreset;
}

export function widgetsForCanvasPreset(preset: ReportCanvasPreset): ReportWidget[] {
  const widgets =
    preset === "playbook-hint"
      ? CHART_WIDGETS.slice(0, 2)
      : preset === "output-summary"
        ? [...OUTPUT_SUMMARY_STATS, ...OUTPUT_SUMMARY_CHARTS]
        : [];
  return widgets.map((widget) => ({ ...widget, id: `${preset}-${widget.id}` }));
}
