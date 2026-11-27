// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";
import { Redirect, useLocation, useParams } from "wouter";
import { useAppStore } from "../features/home/store";
import { levelOfPageId } from "../features/level/level";
import { AnalyseOverview } from "../features/analyse/components/analyse-overview";
import { DataWorkspace } from "../features/analyse/components/data-workspace";
import { InspectWorkspace } from "../features/analyse/components/inspect-workspace";
import { ReportDashboard } from "../features/analyse/components/report-dashboard";
import { builtInInspection } from "../features/analyse/data/inspections";
import { dataPageOf, isDataPageId } from "../features/analyse/lib/data-pages";
import { RecordPages } from "../features/level/record-pages";
import { ProjectLayout } from "../features/project/components/project-layout";
import { WelcomeDialog } from "../features/project/components/welcome-dialog";
import {
  getActiveProjectTab,
  projectAnalyseHref,
  projectTabHref,
  type ProjectTab,
} from "../features/project/lib/project-route";
import { isRunResult, writeScenarioToUrl } from "../features/project/lib/record-scenarios";
import { isWelcomeDialogDisabled } from "../features/project/lib/welcome-preference";
import { useProjectStore } from "../features/project/store/project-store";
import { RunsView } from "../features/runs/components/runs-view";

const TABS: readonly string[] = ["build", "run", "inspect", "analyse"] satisfies ProjectTab[];

// Build, Run, Inspect and Analyse all render through this one component (one
// route, see App.tsx). Build and Inspect show a level's page, read from the
// address: /project/:id/build[/<page id>] and /project/:id/inspect[/<page id>].
// The run result Inspect shows is the record's shown revision (`?scenario=`).
export function ProjectPage() {
  const [location, setLocation] = useLocation();
  const activeTab = getActiveProjectTab(location);
  const { projectId, tab, detailId } = useParams<{
    projectId: string;
    tab?: string;
    detailId?: string;
  }>();
  const project = useAppStore((state) => state.projects.find((item) => item.id === projectId));
  const loadRecord = useProjectStore((state) => state.loadRecord);
  const showScenario = useProjectStore((state) => state.showScenario);
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
  // Start tour never lands on an empty tree.
  const recordStatus = useProjectStore((state) => state.recordStatus);
  const shouldShowWelcome = Boolean(project?.showWelcome && recordStatus === "ready");
  useEffect(() => {
    if (shouldShowWelcome && !isWelcomeDialogDisabled()) openWelcomeDialog();
  }, [shouldShowWelcome, openWelcomeDialog]);
  // Leaving the project (for example browser Back) mustn't carry an open dialog over.
  useEffect(() => closeWelcomeDialog, [projectId, closeWelcomeDialog]);

  // Build shows scenarios only: a result shown on Inspect gives way to its scenario here.
  const shownRevision = record?.info.revisions.find(
    (revision) => revision.name === record.scenario,
  );
  const scenarioOfShownResult = isRunResult(shownRevision) ? (shownRevision?.parent ?? null) : null;
  useEffect(() => {
    if (activeTab === "build" && scenarioOfShownResult) showScenario(scenarioOfShownResult);
  }, [activeTab, scenarioOfShownResult, showScenario]);

  // A Build or Inspect address that names no level goes to the tab's first page.
  const namesNoLevel = Boolean(detailId) && !levelOfPageId(detailId);
  useEffect(() => {
    if ((activeTab === "build" || activeTab === "inspect") && namesNoLevel) {
      setLocation(projectTabHref(projectId, activeTab), { replace: true });
    }
  }, [activeTab, namesNoLevel, projectId, setLocation]);

  // The Analyse address opens a Data page, a report, or a view (built-in or the project's own).
  const selectedViewId = useProjectStore((state) => state.selectedViewId);
  const selectView = useProjectStore((state) => state.selectView);
  const selectedReportId = useProjectStore((state) => state.selectedReportId);
  const selectReport = useProjectStore((state) => state.selectReport);
  const inspections = useProjectStore((state) => state.inspections);
  const inspectionsProjectId = useProjectStore((state) => state.inspectionsProjectId);
  const reports = useProjectStore((state) => state.reports);
  const reportsProjectId = useProjectStore((state) => state.reportsProjectId);
  useEffect(() => {
    if (activeTab !== "analyse") return;
    if (!detailId) {
      if (selectedReportId) selectReport(null);
      if (selectedViewId) selectView(null);
      return;
    }
    // Wait for ProjectLayout to load this project's reports and views.
    if (reportsProjectId !== projectId || inspectionsProjectId !== projectId) return;
    if (isDataPageId(detailId)) {
      if (selectedViewId) selectView(null);
      if (selectedReportId) selectReport(null);
      if (!dataPageOf(detailId)) setLocation(projectAnalyseHref(projectId));
    } else if (reports.some((report) => report.id === detailId)) {
      if (selectedViewId) selectView(null);
      if (selectedReportId !== detailId) selectReport(detailId);
    } else if (builtInInspection(detailId) || inspections.some((view) => view.id === detailId)) {
      if (selectedReportId) selectReport(null);
      if (selectedViewId !== detailId) selectView(detailId);
    } else {
      setLocation(projectAnalyseHref(projectId));
    }
  }, [
    activeTab,
    detailId,
    inspections,
    inspectionsProjectId,
    projectId,
    reports,
    reportsProjectId,
    selectedReportId,
    selectedViewId,
    selectReport,
    selectView,
    setLocation,
  ]);

  // /project/:id, and any tab that isn't one, opens Build (keeping `?scenario=`).
  if (!tab || !TABS.includes(tab)) {
    return (
      <Redirect to={`${projectTabHref(projectId, "build")}${window.location.search}`} replace />
    );
  }

  return (
    <ProjectLayout>
      {(activeTab === "build" || activeTab === "inspect") && (
        <RecordPages key={activeTab} pageId={detailId ?? null} />
      )}

      {activeTab === "run" && <RunsView />}

      {activeTab === "analyse" &&
        (isDataPageId(detailId) ? (
          <DataWorkspace pageId={detailId} />
        ) : selectedViewId ? (
          <InspectWorkspace pageId={selectedViewId} />
        ) : selectedReportId ? (
          <ReportDashboard />
        ) : (
          <AnalyseOverview />
        ))}

      <WelcomeDialog />
    </ProjectLayout>
  );
}
