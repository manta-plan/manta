import type { ProjectStoreSet, UtilityDrawerFlow } from "../types";
import type { RunStatus } from "../../data/runs";

export function createDrawerSlice(set: ProjectStoreSet) {
  return {
    utilityDrawerFlow: null,
    toggleUtilityDrawer: (flow: UtilityDrawerFlow) =>
      set((state) => ({ utilityDrawerFlow: state.utilityDrawerFlow === flow ? null : flow })),
    closeUtilityDrawer: () => set({ utilityDrawerFlow: null }),

    // Layers shares the inner (detail) right stack with the widget and run
    // node config forms, so opening one closes the others.
    isMapLayersDrawerOpen: false,
    toggleMapLayersDrawer: () =>
      set((state) => ({
        isMapLayersDrawerOpen: !state.isMapLayersDrawerOpen,
        isNewWidgetDrawerOpen: false,
        editingWidgetId: null,
        configuringRunNodeId: null,
      })),
    closePageDrawers: () =>
      set({
        isMapLayersDrawerOpen: false,
        isNewWidgetDrawerOpen: false,
        editingWidgetId: null,
        configuringRunNodeId: null,
        tableDrawer: null,
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
          isMapLayersDrawerOpen: false,
        };
      }),
    openWidgetConfigDrawer: (widgetId: string) =>
      set({
        isNewWidgetDrawerOpen: true,
        editingWidgetId: widgetId,
        isNewScenarioDrawerOpen: false,
        isMapLayersDrawerOpen: false,
      }),
    closeNewWidgetDrawer: () => set({ isNewWidgetDrawerOpen: false, editingWidgetId: null }),

    configuringRunNodeId: null,
    openRunNodeConfigDrawer: (nodeId: string) =>
      set({
        configuringRunNodeId: nodeId,
        isNewScenarioDrawerOpen: false,
        isMapLayersDrawerOpen: false,
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

    tableDrawer: null,
    openTableDrawer: (title: string) => set({ tableDrawer: { kind: "catalog", title } }),
    openEntityTable: (ctype: string, carrier: string | null) =>
      set({ tableDrawer: { kind: "entities", ctype, carrier } }),
    openSeriesChart: (entity: string, attribute: string, bus: string | null) =>
      set({ tableDrawer: { kind: "series", entity, attribute, bus } }),
    openScenarioChange: (scenario: string, attribute: string) =>
      set({ tableDrawer: { kind: "scenario-change", scenario, attribute } }),
    openLocationView: (title: string, locations: string[]) =>
      set({ tableDrawer: { kind: "location", title, locations } }),
    closeTableDrawer: () => set({ tableDrawer: null }),

    // Which layer's style controls are open in MapLayersPanel's own
    // internal bottom section (not the app-wide bottom TableDrawer) — see
    // MapLayersPanel.tsx. Independent of the table-drawer state above;
    // they're separate UI surfaces now.
    selectedMapLayerId: null,
    selectMapLayer: (id: string) =>
      set((state) => ({ selectedMapLayerId: state.selectedMapLayerId === id ? null : id })),

    isNewScenarioDrawerOpen: false,
    editingScenarioId: null,
    openNewScenarioDrawer: () =>
      set({
        isNewScenarioDrawerOpen: true,
        editingScenarioId: null,
        itemDrawer: null,
        isNewWidgetDrawerOpen: false,
        editingWidgetId: null,
        configuringRunNodeId: null,
      }),
    openEditScenarioDrawer: (scenarioId: string) =>
      set({
        isNewScenarioDrawerOpen: true,
        editingScenarioId: scenarioId,
        itemDrawer: null,
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
        itemDrawer: null,
        isNewScenarioDrawerOpen: false,
      }),
    openEditRunDrawer: (runId: string) =>
      set({
        isNewRunDrawerOpen: true,
        editingRunId: runId,
        itemDrawer: null,
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
