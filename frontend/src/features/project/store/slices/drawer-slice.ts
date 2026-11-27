// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { ProjectStoreSet, UtilityDrawerFlow } from "../types";

export function createDrawerSlice(set: ProjectStoreSet) {
  return {
    utilityDrawerFlow: null,
    toggleUtilityDrawer: (flow: UtilityDrawerFlow) =>
      set((state) => ({ utilityDrawerFlow: state.utilityDrawerFlow === flow ? null : flow })),
    closeUtilityDrawer: () => set({ utilityDrawerFlow: null }),

    // Closes what a tab opened, on leaving the tab.
    closePageDrawers: () =>
      set({
        configuringRunNodeId: null,
        scenarioChange: null,
        // The Analyse drawers are the tab's own too: they shouldn't reopen on return.
        isNewReportDrawerOpen: false,
        editingReportId: null,
        isNewInspectionDrawerOpen: false,
        editingInspectionId: null,
      }),

    configuringRunNodeId: null,
    openRunNodeConfigDrawer: (nodeId: string) =>
      set({
        configuringRunNodeId: nodeId,
        isNewScenarioDrawerOpen: false,
      }),
    closeRunNodeConfigDrawer: () => set({ configuringRunNodeId: null }),

    isRunFilterDrawerOpen: false,
    openRunFilterDrawer: () => set({ isRunFilterDrawerOpen: true }),
    closeRunFilterDrawer: () => set({ isRunFilterDrawerOpen: false }),

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
        configuringRunNodeId: null,
      }),
    openEditScenarioDrawer: (scenarioId: string) =>
      set({
        isNewScenarioDrawerOpen: true,
        editingScenarioId: scenarioId,
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
  };
}
