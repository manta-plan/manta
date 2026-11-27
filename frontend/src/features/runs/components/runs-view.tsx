import { useEffect } from "react";
import { useParams } from "wouter";
import { useSessionUser } from "../../auth/session";
import { useProjectStore } from "../../project/store/project-store";
import { useRunsStore } from "../store/runs-store";
import { useRunsAutoRefresh } from "../use-runs-auto-refresh";
import { NewRunDrawer } from "./new-run-drawer";
import { RunDetailView } from "./run-detail-view";
import { RunFilterDrawer } from "./run-filter-drawer";
import { RunOverview } from "./run-overview";

// The Run tab: the overview when no run is open, else the run (a draft or a run of the
// backend). The runs list and the filter are in the sidebar; the two left panels open over it.
export function RunsView() {
  // The router only renders this page for signed-in users.
  const owner = useSessionUser()?.username ?? "";
  const { projectId, detailId } = useParams<{ projectId: string; detailId?: string }>();
  const init = useRunsStore((s) => s.init);
  const isNewRunDrawerOpen = useProjectStore((s) => s.isNewRunDrawerOpen);
  const closeNewRunDrawer = useProjectStore((s) => s.closeNewRunDrawer);
  const closeRunFilterDrawer = useProjectStore((s) => s.closeRunFilterDrawer);

  useEffect(() => {
    void init(projectId, owner);
  }, [projectId, owner, init]);

  useRunsAutoRefresh();

  // The two left panels belong to this tab: leaving it should not carry them along.
  useEffect(
    () => () => {
      closeNewRunDrawer();
      closeRunFilterDrawer();
    },
    [closeNewRunDrawer, closeRunFilterDrawer],
  );

  return (
    <div className="relative h-full overflow-hidden">
      {detailId === undefined ? (
        <RunOverview projectId={projectId} />
      ) : (
        <RunDetailView projectId={projectId} runId={detailId} />
      )}
      <NewRunDrawer
        onOpenChange={(open) => !open && closeNewRunDrawer()}
        open={isNewRunDrawerOpen}
      />
      <RunFilterDrawer />
    </div>
  );
}
