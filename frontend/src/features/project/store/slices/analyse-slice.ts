// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { newReportPage, type PageSetup, type ReportBlock } from "../../../analyse/data/reports";
import type { ReportTheme } from "../../../analyse/data/report-themes";
import type { InspectionContent } from "../../../analyse/data/inspections";
import {
  forgetHistory,
  recordEdit,
  stepBack,
  stepForward,
  type EditOptions,
  type ReportHistories,
} from "../../../analyse/lib/report-history";
import { refitPages } from "../../../analyse/lib/report-layout";
import {
  loadProjectInspections,
  saveProjectInspections,
} from "../../../analyse/lib/project-inspections";
import { loadProjectReports, saveProjectReports } from "../../../analyse/lib/project-reports";
import { markDeleted } from "../../../analyse/lib/stored-lists";
import type {
  CreateInspectionInput,
  CreateReportInput,
  InspectionCanvas,
  NewInspectionInput,
  ProjectStoreGet,
  ProjectStoreSet,
  Report,
} from "../types";

// Write-through helper for reports, whose widget edits change them often.
function persistedReports(projectId: string | null, reports: Report[]): Report[] {
  saveProjectReports(projectId, reports);
  return reports;
}

let inspectionSaveTimeout: ReturnType<typeof setTimeout> | undefined;

// What the Analyse tab keeps: the project's views (inspections) and reports,
// which of them is open, and the drawers that make and rename them.
export function createAnalyseSlice(set: ProjectStoreSet, get: ProjectStoreGet) {
  // Writes a waiting inspection edit now, to the project the inspections belong to.
  const flushInspectionSave = () => {
    if (inspectionSaveTimeout === undefined) return;
    clearTimeout(inspectionSaveTimeout);
    inspectionSaveTimeout = undefined;
    saveProjectInspections(get().inspectionsProjectId, get().inspections);
  };
  // Changes one report and records the change for undo. `apply` returns the
  // report as it should become, or the same one when there's nothing to change.
  const editReport = (
    reportId: string,
    label: string,
    mergeKey: string | null,
    apply: (report: Report) => Report,
  ) =>
    set((state) => {
      const report = state.reports.find((item) => item.id === reportId);
      const next = report && apply(report);
      if (!report || !next || next === report) return {};
      return {
        reports: persistedReports(
          state.currentProjectId,
          state.reports.map((item) => (item.id === reportId ? next : item)),
        ),
        reportHistory: recordEdit(state.reportHistory, report, label, mergeKey, Date.now()),
      };
    });
  const stepReport = (reportId: string, step: typeof stepBack) =>
    set((state) => {
      const report = state.reports.find((item) => item.id === reportId);
      const stepped = report && step(state.reportHistory, report);
      if (!report || !stepped) return {};
      return {
        reports: persistedReports(
          state.currentProjectId,
          state.reports.map((item) =>
            item.id === reportId ? { ...item, ...stepped.snapshot } : item,
          ),
        ),
        reportHistory: stepped.histories,
      };
    });

  return {
    selectedViewId: null,
    selectView: (id: string | null) => set({ selectedViewId: id }),
    inspections: [] as InspectionCanvas[],
    inspectionsProjectId: null as string | null,
    loadProjectInspections: (projectId: string) => {
      // An edit of the project being left would otherwise be saved over this one's.
      flushInspectionSave();
      set({
        inspections: loadProjectInspections(projectId),
        inspectionsProjectId: projectId,
        selectedInspectionId: null,
        selectedViewId: null,
      });
    },
    // Leaves selection to the route, so creating one from a widget's menu
    // doesn't pull the user away from the page they're on.
    createInspection: ({ name, description, ...content }: NewInspectionInput) => {
      const inspection: InspectionCanvas = {
        id: `inspection-${Date.now()}`,
        name: name.trim(),
        description: description.trim(),
        ...content,
      };
      set((state) => {
        const inspections = [inspection, ...state.inspections];
        saveProjectInspections(state.currentProjectId, inspections);
        return { inspections, isNewInspectionDrawerOpen: false };
      });
      return inspection;
    },
    updateInspection: (id: string, { name, description }: CreateInspectionInput) =>
      set((state) => {
        const inspections = state.inspections.map((inspection) =>
          inspection.id === id
            ? { ...inspection, name: name.trim(), description: description.trim() }
            : inspection,
        );
        saveProjectInspections(state.currentProjectId, inspections);
        return { inspections, isNewInspectionDrawerOpen: false, editingInspectionId: null };
      }),
    // Panning a map widget changes its inspection every frame, so the save
    // waits for the changes to settle.
    updateInspectionContent: (id: string, content: Partial<InspectionContent>) => {
      set((state) => ({
        inspections: state.inspections.map((inspection) =>
          inspection.id === id ? { ...inspection, ...content } : inspection,
        ),
      }));
      clearTimeout(inspectionSaveTimeout);
      inspectionSaveTimeout = setTimeout(flushInspectionSave, 400);
    },
    deleteInspection: (id: string) =>
      set((state) => {
        markDeleted(id);
        const inspections = state.inspections.filter((inspection) => inspection.id !== id);
        saveProjectInspections(state.currentProjectId, inspections);
        return {
          inspections,
          ...(state.selectedViewId === id ? { selectedViewId: null } : {}),
          // Don't leave the edit form open on an inspection that no longer exists.
          ...(state.editingInspectionId === id
            ? { isNewInspectionDrawerOpen: false, editingInspectionId: null }
            : {}),
        };
      }),
    reports: [] as Report[],
    reportsProjectId: null as string | null,
    loadProjectReports: (projectId: string) =>
      set({
        reports: loadProjectReports(projectId),
        reportsProjectId: projectId,
        selectedReportId: null,
        reportHistory: {},
      }),
    selectedReportId: null,
    selectReport: (id: string | null) => set({ selectedReportId: id }),
    createReport: ({ name, page, theme, pages }: CreateReportInput) => {
      const report: Report = {
        id: `report-${Date.now()}`,
        name: name.trim(),
        createdAt: new Date().toISOString(),
        page,
        theme,
        pages: pages ?? [newReportPage()],
      };
      set((state) => ({
        reports: persistedReports(state.currentProjectId, [report, ...state.reports]),
        selectedReportId: report.id,
        isNewReportDrawerOpen: false,
      }));
      return report;
    },
    updateReport: (id: string, { name, page }: { name: string; page: PageSetup }) =>
      set((state) => {
        const report = state.reports.find((item) => item.id === id);
        const closeDrawer = { isNewReportDrawerOpen: false, editingReportId: null };
        if (!report) return closeDrawer;
        const next = {
          ...report,
          name: name.trim(),
          page,
          pages: refitPages(report.pages, report.page, page),
        };
        return {
          ...closeDrawer,
          reports: persistedReports(
            state.currentProjectId,
            state.reports.map((item) => (item.id === id ? next : item)),
          ),
          reportHistory: recordEdit(
            state.reportHistory,
            report,
            report.page.size !== page.size || report.page.orientation !== page.orientation
              ? "Change paper"
              : "Rename report",
            null,
            Date.now(),
          ),
        };
      }),
    updateReportBlocks: (
      reportId: string,
      pageId: string,
      update: (blocks: ReportBlock[]) => ReportBlock[],
      options?: EditOptions,
    ) =>
      editReport(reportId, options?.label ?? "Edit layout", options?.mergeKey ?? null, (report) => {
        const page = report.pages.find((item) => item.id === pageId);
        const blocks = page && update(page.blocks);
        return page && blocks && blocks !== page.blocks
          ? {
              ...report,
              pages: report.pages.map((item) => (item === page ? { ...page, blocks } : item)),
            }
          : report;
      }),
    setReportTheme: (reportId: string, theme: ReportTheme) =>
      // Sliders and color pickers fire many times a second: one drag is one step.
      editReport(reportId, "Change theme", "theme", (report) => ({ ...report, theme })),
    addReportPage: (reportId: string) =>
      editReport(reportId, "Add page", null, (report) => ({
        ...report,
        pages: [...report.pages, newReportPage()],
      })),
    // A report always keeps at least one page.
    removeReportPage: (reportId: string, pageId: string) =>
      editReport(reportId, "Remove page", null, (report) =>
        report.pages.length > 1
          ? { ...report, pages: report.pages.filter((page) => page.id !== pageId) }
          : report,
      ),
    deleteReport: (id: string) =>
      set((state) => {
        markDeleted(id);
        return {
          reports: persistedReports(
            state.currentProjectId,
            state.reports.filter((report) => report.id !== id),
          ),
          reportHistory: forgetHistory(state.reportHistory, id),
          ...(state.selectedReportId === id ? { selectedReportId: null } : {}),
          ...(state.editingReportId === id
            ? { isNewReportDrawerOpen: false, editingReportId: null }
            : {}),
        };
      }),
    // Another tab saved views or reports: take the stored lists (they include this tab's saved changes).
    refreshFromStorage: () =>
      set((state) => {
        const projectId = state.currentProjectId;
        if (!projectId) return {};
        const reports = state.reportsProjectId === projectId ? loadProjectReports(projectId) : null;
        return {
          // An edit still waiting to be saved would be lost by a reload: keep this tab's list until it is written.
          ...(state.inspectionsProjectId === projectId && inspectionSaveTimeout === undefined
            ? { inspections: loadProjectInspections(projectId) }
            : {}),
          ...(reports
            ? {
                reports,
                // Undo restores whole reports, which would overwrite what the other tab changed.
                reportHistory: reports.reduce((histories, report) => {
                  const mine = state.reports.find((item) => item.id === report.id);
                  return mine && JSON.stringify(mine) !== JSON.stringify(report)
                    ? forgetHistory(histories, report.id)
                    : histories;
                }, state.reportHistory),
              }
            : {}),
        };
      }),
    reportHistory: {} as ReportHistories,
    undoReport: (reportId: string) => stepReport(reportId, stepBack),
    redoReport: (reportId: string) => stepReport(reportId, stepForward),
    isNewReportDrawerOpen: false,
    editingReportId: null as string | null,
    openNewReportDrawer: () =>
      set({
        isNewReportDrawerOpen: true,
        editingReportId: null,
        isNewInspectionDrawerOpen: false,
        editingInspectionId: null,
      }),
    openEditReportDrawer: (reportId: string) =>
      set({
        isNewReportDrawerOpen: true,
        editingReportId: reportId,
        isNewInspectionDrawerOpen: false,
        editingInspectionId: null,
      }),
    closeNewReportDrawer: () => set({ isNewReportDrawerOpen: false, editingReportId: null }),
    isNewInspectionDrawerOpen: false,
    editingInspectionId: null as string | null,
    openNewInspectionDrawer: () =>
      set({
        isNewInspectionDrawerOpen: true,
        editingInspectionId: null,
        isNewReportDrawerOpen: false,
        editingReportId: null,
      }),
    openEditInspectionDrawer: (inspectionId: string) =>
      set({
        isNewInspectionDrawerOpen: true,
        editingInspectionId: inspectionId,
        isNewReportDrawerOpen: false,
        editingReportId: null,
      }),
    closeNewInspectionDrawer: () =>
      set({ isNewInspectionDrawerOpen: false, editingInspectionId: null }),
  };
}
