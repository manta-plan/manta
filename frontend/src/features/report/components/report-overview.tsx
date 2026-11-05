import { LuArrowRight, LuChartBar, LuCircleCheck, LuGitCommitVertical } from "react-icons/lu";
import { DUMMY_RESULT_RUNS } from "../../project/data/inspect-results";
import { startReportWorkspaceTour } from "../../project/lib/workspace-tours";
import { useProjectStore } from "../../project/store/project-store";
import {
  OverviewEmptyStats,
  OverviewSectionHeader,
  OverviewStat,
  OverviewStatGrid,
  OverviewTourButton,
} from "../../inspect/components/workspace-overview-parts";

function HowReportsWork() {
  const reports = useProjectStore((s) => s.reports);
  const scenarioCount = new Set(DUMMY_RESULT_RUNS.map((run) => run.scenarioName)).size;
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title="How Reports Work">
        <OverviewTourButton onClick={startReportWorkspaceTour} />
      </OverviewSectionHeader>
      <div className="divide-surface-700 grid divide-y lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:divide-x lg:divide-y-0">
        <div className="min-h-36 px-5 py-4">
          <div className="text-surface-100 flex items-center gap-2 text-[12px] font-medium">
            <LuGitCommitVertical size={15} className="text-accent-400" />
            Scenario
          </div>
          <p className="text-surface-400 mt-2 text-[12px] leading-5">
            A scenario defines the model and mutations used to produce results.
          </p>
          <div className="text-surface-200 mt-3 text-[11px] font-medium">
            {scenarioCount} available scenarios
          </div>
        </div>
        <div className="text-surface-500 hidden items-center justify-center px-3 lg:flex">
          <LuArrowRight size={15} />
        </div>
        <div className="min-h-36 px-5 py-4">
          <div className="text-surface-100 flex items-center gap-2 text-[12px] font-medium">
            <LuCircleCheck size={15} className="text-ok-500" />
            Run Result
          </div>
          <p className="text-surface-400 mt-2 text-[12px] leading-5">
            A succeeded run provides the output data that a report can visualize.
          </p>
          <div className="text-surface-200 mt-3 text-[11px] font-medium">
            {DUMMY_RESULT_RUNS.length} available run results
          </div>
        </div>
        <div className="text-surface-500 hidden items-center justify-center px-3 lg:flex">
          <LuArrowRight size={15} />
        </div>
        <div className="min-h-36 px-5 py-4">
          <div className="text-surface-100 flex items-center gap-2 text-[12px] font-medium">
            <LuChartBar size={15} className="text-warn-500" />
            Report
          </div>
          <p className="text-surface-400 mt-2 text-[12px] leading-5">
            A report arranges result charts and metrics into a shareable dashboard.
          </p>
          <div className="text-surface-200 mt-3 text-[11px] font-medium">
            {reports.length} existing reports
          </div>
        </div>
      </div>
    </section>
  );
}

function ReportStatistics() {
  const reports = useProjectStore((s) => s.reports);
  const resultIds = new Set(DUMMY_RESULT_RUNS.map((run) => run.id));
  // Only count results that still exist, so a report made before the dummy results doesn't inflate coverage.
  const reportedResultCount = new Set(
    reports.map((report) => report.runId).filter((id) => id !== undefined && resultIds.has(id)),
  ).size;
  const widgetCount = reports.reduce((total, report) => total + report.widgets.length, 0);
  const emptyReportCount = reports.filter((report) => report.widgets.length === 0).length;
  return (
    <OverviewStatGrid title="Report Statistics">
      <OverviewStat label="Reports" value={reports.length} />
      <OverviewStat
        label="Widgets"
        value={widgetCount}
        detail={`${Math.round(widgetCount / reports.length)} per report on average`}
      />
      <OverviewStat
        label="Empty Reports"
        value={emptyReportCount}
        detail={emptyReportCount > 0 ? "No widgets added yet" : undefined}
      />
      <OverviewStat
        label="Run Results Reported"
        value={reportedResultCount}
        detail={`of ${DUMMY_RESULT_RUNS.length} available run results`}
      />
    </OverviewStatGrid>
  );
}

export function ReportOverview() {
  const openNewReportDrawer = useProjectStore((s) => s.openNewReportDrawer);
  const hasReports = useProjectStore((s) => s.reports.length > 0);

  return (
    <div className="bg-surface-900 flex h-full flex-col overflow-y-auto">
      <header className="border-surface-700 flex h-14 shrink-0 items-center border-b px-5">
        <div>
          <h1 className="text-surface-50 text-[14px] font-semibold">Report Workspace</h1>
          <p className="text-surface-400 mt-0.5 text-[11px]">
            Create and organize model result dashboards.
          </p>
        </div>
      </header>

      {hasReports ? (
        <>
          <ReportStatistics />
          <HowReportsWork />
        </>
      ) : (
        <>
          <HowReportsWork />
          <OverviewEmptyStats
            title="Report Statistics"
            message="No reports yet. Create one to turn a run result into a dashboard."
            action={{ label: "New Report", onClick: () => openNewReportDrawer() }}
          />
        </>
      )}
    </div>
  );
}
