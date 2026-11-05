import { LuCircleCheck } from "react-icons/lu";
import { DUMMY_RESULT_RUNS, runLabel } from "../../project/data/inspect-results";
import { useProjectStore } from "../../project/store/project-store";

// The demo's run results, independent of the project's runs. Picking one
// opens the New Report form with it prefilled.
export function ReportResultsPanel() {
  const openNewReportDrawer = useProjectStore((s) => s.openNewReportDrawer);
  const isDrawerOpen = useProjectStore((s) => s.isNewReportDrawerOpen);
  const prefilledId = useProjectStore((s) => s.newReportResultId);

  return (
    <div className="h-full overflow-y-auto py-1">
      {DUMMY_RESULT_RUNS.map((run, index) => {
        const isSelected = isDrawerOpen && prefilledId === run.id;
        return (
          <div
            key={run.id}
            data-tour={index === 0 ? "report-result-item" : undefined}
            onClick={() => openNewReportDrawer(run.id)}
            title={run.scenarioName}
            className={`flex h-[26px] cursor-default items-center gap-1.5 px-3 text-[12px] ${
              isSelected
                ? "bg-accent-600/25 text-surface-50"
                : "text-surface-200 hover:bg-surface-700/60"
            }`}
          >
            <LuCircleCheck size={12} className="text-ok-500 shrink-0" />
            <span className="truncate">{runLabel(run)}</span>
            {run.duration && (
              <span className="text-surface-500 ml-auto shrink-0 text-[11px]">{run.duration}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
