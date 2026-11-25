// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

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

// The frame of a project: header, sidebar, the active tab in the middle, the
// scenario change drawer that opens over it, and the footer.
export function ProjectLayout({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const setCurrentProjectId = useProjectStore((s) => s.setCurrentProjectId);
  const closePageDrawers = useProjectStore((s) => s.closePageDrawers);
  const loadProjectDrafts = useProjectStore((s) => s.loadProjectDrafts);
  const [location] = useLocation();
  const activeTab = getActiveProjectTab(location);

  useEffect(() => {
    setCurrentProjectId(projectId);
    loadProjectDrafts(projectId);
    useLevelStore.getState().resetForProject();
  }, [projectId, setCurrentProjectId, loadProjectDrafts]);

  // The scenario change table belongs to the tab that opened it; leaving the tab (or project) shouldn't carry it along.
  useEffect(() => {
    closePageDrawers();
  }, [activeTab, closePageDrawers, projectId]);

  return (
    <div className="bg-surface-900 flex h-svh w-full flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        {/* Build and Inspect: the record's scenarios over its tree. Run: the runs and the playbooks to run. The other tabs fill the page. */}
        {(activeTab === "build" || activeTab === "inspect" || activeTab === "run") && <Sidebar />}
        <main data-tour="run-main-section" className="relative flex-1 overflow-hidden">
          {children}
          <RightDrawer />
        </main>
      </div>
      <Footer />
      {(activeTab === "build" || activeTab === "inspect") && <ScenarioChangeDrawer />}
      {(activeTab === "build" || activeTab === "inspect") && <ScenarioDialogs />}
    </div>
  );
}
