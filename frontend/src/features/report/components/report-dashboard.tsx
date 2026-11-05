import type { ReactNode } from "react";
import { LuCalendarClock, LuChartBar, LuLayoutGrid } from "react-icons/lu";
import { StatCard } from "./stat-card";
import { ChartCard } from "./chart-card";
import { useProjectStore } from "../../project/store/project-store";
import { DUMMY_RESULT_RUNS, runLabel } from "../../project/data/inspect-results";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-surface-300 text-[11px] font-semibold tracking-wide uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

// Reports created with the "Start blank" canvas have no widgets and show an
// empty canvas until widgets are added through the widget config form; the
// other presets start pre-populated (see widgetsForCanvasPreset).
export function ReportDashboard() {
  const selectedReportId = useProjectStore((s) => s.selectedReportId);
  const reports = useProjectStore((s) => s.reports);
  const toggleNewWidgetDrawer = useProjectStore((s) => s.toggleNewWidgetDrawer);

  const report = reports.find((r) => r.id === selectedReportId);
  if (!report) return null;

  const result = DUMMY_RESULT_RUNS.find((item) => item.id === report.runId);
  const statWidgets = report.widgets.filter((widget) => widget.widgetType === "stat");
  const chartWidgets = report.widgets.filter((widget) => widget.widgetType === "chart");

  return (
    <div className="bg-surface-900 flex h-full w-full flex-col overflow-hidden">
      <header className="border-surface-700 flex min-h-14 shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b px-5 py-2">
        <div className="mr-auto min-w-0">
          <h1 className="text-surface-50 truncate text-[14px] font-semibold">{report.name}</h1>
          <p className="text-surface-400 mt-0.5 flex items-center gap-1.5 truncate text-[11px]">
            <LuChartBar size={12} className="shrink-0" />
            {result ? runLabel(result) : report.scenarioName}
          </p>
        </div>
        <div className="text-surface-400 flex items-center gap-1.5 text-[11px]">
          <LuCalendarClock size={13} />
          Generated {report.generatedAt.toLowerCase()}
        </div>
      </header>

      {report.widgets.length === 0 ? (
        <div className="text-surface-500 flex flex-1 flex-col items-center justify-center gap-3 text-center">
          <LuLayoutGrid size={20} />
          <span className="text-[12px]">This report is blank. Add a widget to get started.</span>
          <button
            onClick={() => toggleNewWidgetDrawer()}
            className="bg-accent-600 hover:bg-accent-500 flex items-center gap-1.5 rounded px-3 py-1.5 text-[12px] font-medium text-white outline-none"
          >
            <LuLayoutGrid size={13} />
            Add Widget
          </button>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5">
          {statWidgets.length > 0 && (
            <Section title="Key Metrics">
              <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                {statWidgets.map((widget) => (
                  <StatCard key={widget.id} widget={widget} />
                ))}
              </div>
            </Section>
          )}
          {chartWidgets.length > 0 && (
            <Section title="Charts">
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {chartWidgets.map((widget) => (
                  <ChartCard key={widget.id} widget={widget} />
                ))}
              </div>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}
