import { useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { builtInInspection } from "../features/project/data/inspections";
import { ReportDashboard } from "../features/report/components/report-dashboard";
import { ReportOverview } from "../features/report/components/report-overview";
import { InspectOverview } from "../features/inspect/components/inspect-overview";
import { InspectWorkspace } from "../features/inspect/components/inspect-workspace";
import { useAppStore } from "../features/home/store";
import { MapView } from "../features/project/components/map-view";
import { ProjectLayout } from "../features/project/components/project-layout";
import { WelcomeDialog } from "../features/project/components/welcome-dialog";
import {
  getActiveProjectTab,
  projectInspectHref,
  projectReportHref,
} from "../features/project/lib/project-route";
import { writeScenarioToUrl } from "../features/project/lib/record-scenarios";
import { isWelcomeDialogDisabled } from "../features/project/lib/welcome-preference";
import { useProjectStore } from "../features/project/store/project-store";
import { RunsView } from "../features/runs/components/runs-view";

// Model, Run, Inspect and Report all render through this one component (one
// route, see App.tsx) so MapView stays mounted, just hidden, when switching
// tabs. That keeps the maplibre instance and its already-loaded tiles and style
// alive instead of starting the map again on every tab switch.
export function ProjectPage() {
  const [location, setLocation] = useLocation();
  const activeTab = getActiveProjectTab(location);
  const { projectId, detailId } = useParams<{ projectId: string; detailId?: string }>();
  const selectedInspectionId = useProjectStore((state) => state.selectedInspectionId);
  const selectInspection = useProjectStore((state) => state.selectInspection);
  const inspections = useProjectStore((state) => state.inspections);
  const inspectionsProjectId = useProjectStore((state) => state.inspectionsProjectId);
  const selectedReportId = useProjectStore((state) => state.selectedReportId);
  const selectReport = useProjectStore((state) => state.selectReport);
  const reports = useProjectStore((state) => state.reports);
  const reportsProjectId = useProjectStore((state) => state.reportsProjectId);
  const project = useAppStore((state) => state.projects.find((item) => item.id === projectId));
  const loadRecord = useProjectStore((state) => state.loadRecord);
  const openWelcomeDialog = useProjectStore((state) => state.openWelcomeDialog);
  const closeWelcomeDialog = useProjectStore((state) => state.closeWelcomeDialog);

  // The project's record (see the record slice); kept when the next project uses
  // the same one.
  const recordId = project?.recordId ?? null;
  useEffect(() => {
    loadRecord(recordId);
  }, [loadRecord, recordId]);

  // Navigating drops the query string: keep `?scenario=` on every URL.
  const record = useProjectStore((state) => state.record);
  useEffect(() => {
    if (record) writeScenarioToUrl(record.info, record.scenario);
  }, [location, record]);

  // First open of a new project, held back until the record has loaded so that
  // Start tour never lands on an empty tree and map.
  const recordStatus = useProjectStore((state) => state.recordStatus);
  const shouldShowWelcome = Boolean(project?.showWelcome && recordStatus === "ready");
  useEffect(() => {
    if (shouldShowWelcome && !isWelcomeDialogDisabled()) openWelcomeDialog();
  }, [shouldShowWelcome, openWelcomeDialog]);
  // Leaving the project (for example browser Back) mustn't carry an open dialog over.
  useEffect(() => closeWelcomeDialog, [projectId, closeWelcomeDialog]);

  useEffect(() => {
    if (activeTab !== "inspect") return;
    if (!detailId) {
      if (selectedInspectionId) selectInspection(null);
      return;
    }
    // ProjectLayout loads the project's inspections in an effect that runs after
    // this one, so on a fresh load of an inspection URL the list is still empty.
    // Wait for it rather than redirecting to the overview.
    if (inspectionsProjectId !== projectId) return;
    if (!builtInInspection(detailId) && !inspections.some((canvas) => canvas.id === detailId)) {
      setLocation(projectInspectHref(projectId));
      return;
    }
    if (selectedInspectionId !== detailId) selectInspection(detailId);
  }, [
    activeTab,
    detailId,
    inspections,
    inspectionsProjectId,
    projectId,
    selectedInspectionId,
    selectInspection,
    setLocation,
  ]);

  useEffect(() => {
    if (activeTab !== "report") return;
    if (!detailId) {
      if (selectedReportId) selectReport(null);
      return;
    }
    // Wait for ProjectLayout to load this project's reports (see inspections).
    if (reportsProjectId !== projectId) return;
    if (!reports.some((report) => report.id === detailId)) {
      setLocation(projectReportHref(projectId));
      return;
    }
    if (selectedReportId !== detailId) selectReport(detailId);
  }, [
    activeTab,
    detailId,
    projectId,
    reports,
    reportsProjectId,
    selectedReportId,
    selectReport,
    setLocation,
  ]);

  return (
    <ProjectLayout>
      {/* Hidden with opacity + inert, not just `invisible`: maplibre's CSS sets
          `visibility: visible` on the expanded compact attribution, which
          overrides an inherited `visibility: hidden` and leaked the Carto/OSM
          credits onto the other tabs. */}
      <div
        aria-hidden={activeTab !== "model"}
        inert={activeTab !== "model"}
        className={
          activeTab === "model"
            ? "h-full w-full"
            : "pointer-events-none invisible absolute inset-0 h-full w-full opacity-0"
        }
      >
        <MapView isVisible={activeTab === "model"} />
      </div>

      {activeTab === "run" && <RunsView />}

      {activeTab === "inspect" &&
        (selectedInspectionId ? <InspectWorkspace /> : <InspectOverview />)}

      {activeTab === "report" && (selectedReportId ? <ReportDashboard /> : <ReportOverview />)}

      <WelcomeDialog />
    </ProjectLayout>
  );
}
