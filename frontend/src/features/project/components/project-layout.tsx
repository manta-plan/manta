import { useEffect, type ReactNode } from "react";
import { useLocation, useParams } from "wouter";
import { getActiveProjectTab } from "../lib/project-route";
import { useProjectStore } from "../store/project-store";
import { InspectionFilterDrawer } from "../../inspect/components/workspace-filter-drawers";
import { NewInspectionDrawer } from "../../inspect/components/new-inspection-drawer";
import { Footer } from "./footer";
import { Header } from "./header";
import { ModelItemDrawer } from "./model-item-drawer";
import { RightDrawer } from "./right-drawer";
import { Sidebar } from "./sidebar";
import { TableDrawer } from "./table-drawer";

// The frame of a project: header, sidebar, the active tab in the middle, the
// drawers that open over it, and the footer.
export function ProjectLayout({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const setCurrentProjectId = useProjectStore((s) => s.setCurrentProjectId);
  const loadProjectInspections = useProjectStore((s) => s.loadProjectInspections);
  const closePageDrawers = useProjectStore((s) => s.closePageDrawers);
  const [location] = useLocation();
  const activeTab = getActiveProjectTab(location);

  useEffect(() => {
    setCurrentProjectId(projectId);
    loadProjectInspections(projectId);
  }, [loadProjectInspections, projectId, setCurrentProjectId]);

  // The bottom table and the inner right drawer stack belong to the tab that
  // opened them; leaving the tab (or project) shouldn't carry them along.
  useEffect(() => {
    closePageDrawers();
  }, [activeTab, closePageDrawers, projectId]);

  return (
    <div className="bg-surface-900 flex h-full w-full flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        {/* The model tree and the record's scenarios, or the inspections; the other tabs fill the page. */}
        {(activeTab === "model" || activeTab === "inspect") && <Sidebar />}
        <main data-tour="run-main-section" className="relative flex-1 overflow-hidden">
          {children}
          <ModelItemDrawer />
          <NewInspectionDrawer />
          <InspectionFilterDrawer />
          <RightDrawer />
        </main>
      </div>
      <Footer />
      <TableDrawer />
    </div>
  );
}
