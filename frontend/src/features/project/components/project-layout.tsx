import { useEffect, type ReactNode } from "react";
import { useLocation, useParams } from "wouter";
import { getActiveProjectTab } from "../lib/project-route";
import { useLevelStore } from "../../level/level-store";
import { ScenarioChangeDrawer } from "../../level/scenarios/scenario-change-drawer";
import { ScenarioDialogs } from "../../level/scenarios/scenario-dialogs";
import { useProjectStore } from "../store/project-store";
import { Footer } from "./footer";
import { Header } from "./header";
import { RightDrawer } from "./right-drawer";
import { Sidebar } from "./sidebar";
import { AnalyseSidebar } from "../../analyse/components/analyse-sidebar";
import { NewInspectionDrawer } from "../../analyse/components/new-inspection-drawer";
import { NewReportDrawer } from "../../analyse/components/new-report-drawer";
import { PROJECT_INSPECTIONS_STORAGE_KEY } from "../../analyse/lib/project-inspections";
import { PROJECT_REPORTS_STORAGE_KEY } from "../../analyse/lib/project-reports";

// The frame of a project: header, sidebar, the active tab in the middle, the
// scenario change drawer that opens over it, and the footer.
export function ProjectLayout({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const setCurrentProjectId = useProjectStore((s) => s.setCurrentProjectId);
  const closePageDrawers = useProjectStore((s) => s.closePageDrawers);
  const loadProjectDrafts = useProjectStore((s) => s.loadProjectDrafts);
  const loadProjectInspections = useProjectStore((s) => s.loadProjectInspections);
  const loadProjectReports = useProjectStore((s) => s.loadProjectReports);
  const [location] = useLocation();
  const activeTab = getActiveProjectTab(location);

  useEffect(() => {
    setCurrentProjectId(projectId);
    loadProjectDrafts(projectId);
    loadProjectInspections(projectId);
    loadProjectReports(projectId);
    useLevelStore.getState().resetForProject();
  }, [
    projectId,
    setCurrentProjectId,
    loadProjectDrafts,
    loadProjectInspections,
    loadProjectReports,
  ]);

  // Another tab of the app saved this project's views or reports: show them here too.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (
        event.key === PROJECT_INSPECTIONS_STORAGE_KEY ||
        event.key === PROJECT_REPORTS_STORAGE_KEY
      )
        useProjectStore.getState().refreshFromStorage();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // The scenario change table belongs to the tab that opened it; leaving the tab (or project) shouldn't carry it along.
  useEffect(() => {
    closePageDrawers();
  }, [activeTab, closePageDrawers, projectId]);

  return (
    <div className="bg-surface-900 flex h-svh w-full flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        {/* Build and Inspect: the record's scenarios over its tree. Run: the runs and the playbooks to run. Analyse: its data, views and reports. */}
        {(activeTab === "build" || activeTab === "inspect" || activeTab === "run") && <Sidebar />}
        {activeTab === "analyse" && <AnalyseSidebar />}
        <main data-tour="run-main-section" className="relative flex-1 overflow-hidden">
          {children}
          <RightDrawer />
        </main>
      </div>
      <Footer />
      {(activeTab === "build" || activeTab === "inspect") && <ScenarioChangeDrawer />}
      {(activeTab === "build" || activeTab === "inspect") && <ScenarioDialogs />}
      {activeTab === "analyse" && <NewReportDrawer />}
      {activeTab === "analyse" && <NewInspectionDrawer />}
    </div>
  );
}
