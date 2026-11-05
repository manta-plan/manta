import { LuArrowRight, LuCircleCheck, LuFiles, LuGitCompareArrows } from "react-icons/lu";
import { DUMMY_RESULT_RUNS } from "../../project/data/inspect-results";
import { BUILT_IN_INSPECTIONS } from "../../project/data/inspections";
import { startInspectWorkspaceTour } from "../../project/lib/workspace-tours";
import { useProjectStore } from "../../project/store/project-store";
import {
  OverviewSectionHeader,
  OverviewStat,
  OverviewStatGrid,
  OverviewTourButton,
} from "./workspace-overview-parts";

function HowInspectionsWork() {
  const inspections = useProjectStore((s) => s.inspections);
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title="How Inspections Work">
        <OverviewTourButton onClick={startInspectWorkspaceTour} />
      </OverviewSectionHeader>
      <div className="divide-surface-700 grid divide-y lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:divide-x lg:divide-y-0">
        <div className="min-h-36 px-5 py-4">
          <div className="text-surface-100 flex items-center gap-2 text-[12px] font-medium">
            <LuCircleCheck size={15} className="text-ok-500" />
            Run Result
          </div>
          <p className="text-surface-400 mt-2 text-[12px] leading-5">
            A succeeded run produces a run result you can inspect.
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
            <LuFiles size={15} className="text-accent-400" />
            Inspection
          </div>
          <p className="text-surface-400 mt-2 text-[12px] leading-5">
            An inspection is a page of widgets for one review task, such as dispatch or costs. Start
            from a built-in one or build your own.
          </p>
          <div className="text-surface-200 mt-3 text-[11px] font-medium">
            {BUILT_IN_INSPECTIONS.length} built-in · {inspections.length} of your own
          </div>
        </div>
        <div className="text-surface-500 hidden items-center justify-center px-3 lg:flex">
          <LuArrowRight size={15} />
        </div>
        <div className="min-h-36 px-5 py-4">
          <div className="text-surface-100 flex items-center gap-2 text-[12px] font-medium">
            <LuGitCompareArrows size={15} className="text-warn-500" />
            Comparison
          </div>
          <p className="text-surface-400 mt-2 text-[12px] leading-5">
            Compare run results across scenarios to understand model changes.
          </p>
          <div className="text-surface-200 mt-3 text-[11px] font-medium">
            {inspections.filter((inspection) => inspection.comparisonResultId).length} of your
            inspections compare
          </div>
        </div>
      </div>
    </section>
  );
}

function InspectionStatistics() {
  const inspections = useProjectStore((s) => s.inspections);
  const inspectedResults = new Set(
    inspections.map((inspection) => inspection.resultId ?? DUMMY_RESULT_RUNS[0].id),
  );
  const widgetCount = inspections.reduce((sum, inspection) => sum + inspection.items.length, 0);
  return (
    <OverviewStatGrid title="Inspection Statistics">
      <OverviewStat
        label="Your Inspections"
        value={inspections.length}
        detail={`plus ${BUILT_IN_INSPECTIONS.length} built-in`}
      />
      <OverviewStat label="Widgets" value={widgetCount} detail="across your inspections" />
      <OverviewStat
        label="Run Results Inspected"
        value={inspections.length > 0 ? inspectedResults.size : 0}
        detail={`of ${DUMMY_RESULT_RUNS.length} available run results`}
      />
      <OverviewStat
        label="Comparisons"
        value={inspections.filter((inspection) => inspection.comparisonResultId).length}
      />
    </OverviewStatGrid>
  );
}

export function InspectOverview() {
  return (
    <div
      data-tour="inspect-main-section"
      className="bg-surface-900 flex h-full flex-col overflow-y-auto"
    >
      <header className="border-surface-700 flex h-14 shrink-0 items-center border-b px-5">
        <div>
          <h1 className="text-surface-50 text-[14px] font-semibold">Inspect Workspace</h1>
          <p className="text-surface-400 mt-0.5 text-[11px]">
            Review, compare, and validate completed model outputs.
          </p>
        </div>
      </header>
      <InspectionStatistics />
      <HowInspectionsWork />
    </div>
  );
}
