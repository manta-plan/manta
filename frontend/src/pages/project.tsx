import { useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useAppStore } from "../features/home/store";
import { MapView } from "../features/project/components/map-view";
import { ProjectLayout } from "../features/project/components/project-layout";
import { WelcomeDialog } from "../features/project/components/welcome-dialog";
import { getActiveProjectTab } from "../features/project/lib/project-route";
import { writeScenarioToUrl } from "../features/project/lib/record-scenarios";
import { isWelcomeDialogDisabled } from "../features/project/lib/welcome-preference";
import { useProjectStore } from "../features/project/store/project-store";
import { RunsView } from "../features/runs/components/runs-view";

// Model, Run, Inspect and Report all render through this one component (one
// route, see App.tsx) so MapView stays mounted, just hidden, when switching
// tabs. That keeps the maplibre instance and its already-loaded tiles and style
// alive instead of starting the map again on every tab switch.
export function ProjectPage() {
  const [location] = useLocation();
  const activeTab = getActiveProjectTab(location);
  const { projectId } = useParams<{ projectId: string }>();
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

      {/* Inspect and Report arrive with their own tabs. */}
      {(activeTab === "inspect" || activeTab === "report") && (
        <div className="text-surface-400 flex h-full items-center justify-center text-sm">
          This tab is not available yet.
        </div>
      )}

      <WelcomeDialog />
    </ProjectLayout>
  );
}
