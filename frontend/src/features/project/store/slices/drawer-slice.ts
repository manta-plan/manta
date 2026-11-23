import type { ProjectStoreSet, UtilityDrawerFlow } from "../types";
import type { RunStatus } from "../../data/runs";

export function createDrawerSlice(set: ProjectStoreSet) {
  return {
    utilityDrawerFlow: null,
    toggleUtilityDrawer: (flow: UtilityDrawerFlow) =>
      set((state) => ({ utilityDrawerFlow: state.utilityDrawerFlow === flow ? null : flow })),
    closeUtilityDrawer: () => set({ utilityDrawerFlow: null }),

    // Closes what a tab opened, on leaving the tab.
    closePageDrawers: () =>
      set({
        isNewWidgetDrawerOpen: false,
        editingWidgetId: null,
        configuringRunNodeId: null,
        scenarioChange: null,
      }),

    isNewWidgetDrawerOpen: false,
    editingWidgetId: null,
    toggleNewWidgetDrawer: () =>
      set((state) => {
        const next = !state.isNewWidgetDrawerOpen;
        return {
          isNewWidgetDrawerOpen: next,
          editingWidgetId: next ? null : state.editingWidgetId,
          isNewScenarioDrawerOpen: false,
        };
      }),
    openWidgetConfigDrawer: (widgetId: string) =>
      set({
        isNewWidgetDrawerOpen: true,
        editingWidgetId: widgetId,
        isNewScenarioDrawerOpen: false,
      }),
    closeNewWidgetDrawer: () => set({ isNewWidgetDrawerOpen: false, editingWidgetId: null }),

    configuringRunNodeId: null,
    openRunNodeConfigDrawer: (nodeId: string) =>
      set({
        configuringRunNodeId: nodeId,
        isNewScenarioDrawerOpen: false,
      }),
    closeRunNodeConfigDrawer: () => set({ configuringRunNodeId: null }),

    isRunFilterDrawerOpen: false,
    runStatusFilters: [],
    openRunFilterDrawer: () => set({ isRunFilterDrawerOpen: true }),
    closeRunFilterDrawer: () => set({ isRunFilterDrawerOpen: false }),
    toggleRunStatusFilter: (status: RunStatus) =>
      set((state) => ({
        runStatusFilters: state.runStatusFilters.includes(status)
          ? state.runStatusFilters.filter((item) => item !== status)
          : [...state.runStatusFilters, status],
      })),
    clearRunFilters: () => set({ runStatusFilters: [] }),

    isInspectionFilterDrawerOpen: false,
    inspectionFilters: [],
    openInspectionFilterDrawer: () => set({ isInspectionFilterDrawerOpen: true }),
    closeInspectionFilterDrawer: () => set({ isInspectionFilterDrawerOpen: false }),
    toggleInspectionFilter: (filter: string) =>
      set((state) => ({
        inspectionFilters: state.inspectionFilters.includes(filter)
          ? state.inspectionFilters.filter((item) => item !== filter)
          : [...state.inspectionFilters, filter],
      })),
    clearInspectionFilters: () => set({ inspectionFilters: [] }),

    isReportFilterDrawerOpen: false,
    reportFilters: [],
    openReportFilterDrawer: () => set({ isReportFilterDrawerOpen: true }),
    closeReportFilterDrawer: () => set({ isReportFilterDrawerOpen: false }),
    toggleReportFilter: (filter: string) =>
      set((state) => ({
        reportFilters: state.reportFilters.includes(filter)
          ? state.reportFilters.filter((item) => item !== filter)
          : [...state.reportFilters, filter],
      })),
    clearReportFilters: () => set({ reportFilters: [] }),

    // The attribute a Scenarios panel change row shows in the bottom drawer.
    scenarioChange: null as { scenario: string; attribute: string } | null,
    openScenarioChange: (scenario: string, attribute: string) =>
      set({ scenarioChange: { scenario, attribute } }),
    closeScenarioChange: () => set({ scenarioChange: null }),

    isNewScenarioDrawerOpen: false,
    editingScenarioId: null,
    openNewScenarioDrawer: () =>
      set({
        isNewScenarioDrawerOpen: true,
        editingScenarioId: null,
        isNewWidgetDrawerOpen: false,
        editingWidgetId: null,
        configuringRunNodeId: null,
      }),
    openEditScenarioDrawer: (scenarioId: string) =>
      set({
        isNewScenarioDrawerOpen: true,
        editingScenarioId: scenarioId,
        isNewWidgetDrawerOpen: false,
        editingWidgetId: null,
        configuringRunNodeId: null,
      }),
    closeNewScenarioDrawer: () => set({ isNewScenarioDrawerOpen: false, editingScenarioId: null }),

    newMutationScenarioId: null,
    openNewMutationDrawer: (scenarioId: string) =>
      set({ newMutationScenarioId: scenarioId, isNewScenarioDrawerOpen: false }),
    closeNewMutationDrawer: () => set({ newMutationScenarioId: null }),

    isNewRunDrawerOpen: false,
    editingRunId: null,
    openNewRunDrawer: () =>
      set({
        isNewRunDrawerOpen: true,
        editingRunId: null,
        isNewScenarioDrawerOpen: false,
      }),
    openEditRunDrawer: (runId: string) =>
      set({
        isNewRunDrawerOpen: true,
        editingRunId: runId,
        isNewScenarioDrawerOpen: false,
      }),
    closeNewRunDrawer: () => set({ isNewRunDrawerOpen: false, editingRunId: null }),

    isNewReportDrawerOpen: false,
    editingReportId: null,
    newReportResultId: null,
    openNewReportDrawer: (resultId?: string) =>
      set({
        isNewReportDrawerOpen: true,
        editingReportId: null,
        newReportResultId: resultId ?? null,
        isNewScenarioDrawerOpen: false,
      }),
    openEditReportDrawer: (reportId: string) =>
      set({
        isNewReportDrawerOpen: true,
        editingReportId: reportId,
        isNewScenarioDrawerOpen: false,
      }),
    closeNewReportDrawer: () =>
      set({ isNewReportDrawerOpen: false, editingReportId: null, newReportResultId: null }),

    isNewInspectionDrawerOpen: false,
    editingInspectionId: null,
    openNewInspectionDrawer: () =>
      set({
        isNewInspectionDrawerOpen: true,
        editingInspectionId: null,
        isNewScenarioDrawerOpen: false,
      }),
    openEditInspectionDrawer: (inspectionId: string) =>
      set({
        isNewInspectionDrawerOpen: true,
        editingInspectionId: inspectionId,
        isNewScenarioDrawerOpen: false,
      }),
    closeNewInspectionDrawer: () =>
      set({ isNewInspectionDrawerOpen: false, editingInspectionId: null }),
  };
}
