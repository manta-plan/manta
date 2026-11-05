import { widgetsForCanvasPreset } from "../../data/reports";
import type { ReportWidget } from "../../data/report-widgets";
import { INITIAL_RUNS } from "../../data/runs";
import { INITIAL_SCENARIOS } from "../../data/scenarios";
import type { ScenarioMutation } from "../../data/scenarios";
import { loadProjectScenarios, saveProjectScenarios } from "../../lib/project-scenarios";
import { loadProjectRuns, saveProjectRuns } from "../../lib/project-runs";
import { loadProjectInspections, saveProjectInspections } from "../../lib/project-inspections";
import type { InspectionContent } from "../../data/inspections";
import { loadProjectReports, saveProjectReports } from "../../lib/project-reports";
import type {
  ProjectStoreGet,
  ProjectStoreSet,
  CreateInspectionInput,
  CreateReportInput,
  NewInspectionInput,
  CreateRunInput,
  CreateScenarioDirectMutationInput,
  CreateScenarioInput,
  CreateScenarioMutationInput,
  InspectionCanvas,
  Report,
  Run,
  Scenario,
} from "../types";

// Writes through to localStorage as a side effect and hands the same array
// back, so every runs-mutating set() call can just wrap its `runs:` value
// in this instead of remembering a separate saveProjectRuns() call.
function persisted(projectId: string | null, runs: Run[]): Run[] {
  saveProjectRuns(projectId, runs);
  return runs;
}

// Same write-through helper for reports, whose widget edits change them often.
function persistedReports(projectId: string | null, reports: Report[]): Report[] {
  saveProjectReports(projectId, reports);
  return reports;
}

let inspectionSaveTimeout: ReturnType<typeof setTimeout> | undefined;

export function createScenarioRunReportSlice(set: ProjectStoreSet, get: ProjectStoreGet) {
  return {
    scenarios: INITIAL_SCENARIOS,
    scenarioSelection: { scenarioId: INITIAL_SCENARIOS[0].id, mutationId: null },
    loadProjectScenarios: (projectId: string) => {
      const scenarios = loadProjectScenarios(projectId);
      set({
        scenarios,
        scenarioSelection: { scenarioId: scenarios[0].id, mutationId: null },
        newMutationScenarioId: null,
        isNewScenarioDrawerOpen: false,
      });
    },
    createScenario: ({ name, baseScenarioId, baseModelSourceIds }: CreateScenarioInput) => {
      let scenario!: Scenario;
      set((state) => {
        scenario = {
          id: `scenario-${Date.now()}`,
          name: name.trim(),
          modelResolution:
            state.scenarios.find((item) => item.id === baseScenarioId)?.modelResolution ?? "nodal",
          baseScenarioId,
          baseModelSourceIds,
          mutations: [],
        };
        const scenarios = [...state.scenarios, scenario];
        saveProjectScenarios(state.currentProjectId, scenarios);
        return {
          scenarios,
          scenarioSelection: { scenarioId: scenario.id, mutationId: null },
          isNewScenarioDrawerOpen: false,
        };
      });
      return scenario;
    },
    // The root scenario ('scenario-base') is excluded — its display name is
    // hardcoded by id (see scenarioListTitle in ScenariosPanel.tsx) so a
    // rename wouldn't visibly do anything, and several places assume it
    // always exists, so it also can't be deleted.
    renameScenario: (id: string, name: string) => {
      const trimmed = name.trim();
      if (!trimmed || id === "scenario-base") return;
      set((state) => {
        const scenarios = state.scenarios.map((scenario) =>
          scenario.id === id ? { ...scenario, name: trimmed } : scenario,
        );
        saveProjectScenarios(state.currentProjectId, scenarios);
        return { scenarios };
      });
    },
    deleteScenario: (id: string) => {
      if (id === "scenario-base") return;
      set((state) => {
        // Also removes any scenario based on this one, so deleting a
        // scenario that's itself a base for others doesn't orphan them.
        const removedIds = new Set([
          id,
          ...state.scenarios
            .filter((scenario) => scenario.baseScenarioId === id)
            .map((scenario) => scenario.id),
        ]);
        const scenarios = state.scenarios.filter((scenario) => !removedIds.has(scenario.id));
        saveProjectScenarios(state.currentProjectId, scenarios);
        const wasActive = removedIds.has(state.scenarioSelection.scenarioId);
        return {
          scenarios,
          ...(wasActive
            ? {
                scenarioSelection: { scenarioId: "scenario-base", mutationId: null },
                itemDrawer: null,
              }
            : {}),
        };
      });
    },
    createScenarioMutation: ({ scenarioId, name, targetId, rule }: CreateScenarioMutationInput) => {
      let mutation: ScenarioMutation | null = null;
      set((state) => {
        const scenario = state.scenarios.find((item) => item.id === scenarioId);
        if (!scenario?.baseScenarioId) return {};
        const nextMutation: ScenarioMutation = {
          id: `mutation-${Date.now()}`,
          targetId,
          op: "modify" as const,
          kind: "rule" as const,
          description: `${rule.property} ${rule.operation} ${rule.value} where ${rule.filterField} = ${rule.filterValue}`,
          rule,
          name: name.trim(),
        };
        mutation = nextMutation;
        const scenarios = state.scenarios.map((item) =>
          item.id === scenarioId ? { ...item, mutations: [...item.mutations, nextMutation] } : item,
        );
        saveProjectScenarios(state.currentProjectId, scenarios);
        return {
          scenarios,
          scenarioSelection: { scenarioId, mutationId: nextMutation.id },
          newMutationScenarioId: null,
        };
      });
      return mutation;
    },
    createScenarioDirectMutation: ({
      scenarioId,
      name,
      targetId,
      direct,
    }: CreateScenarioDirectMutationInput) => {
      let mutation: ScenarioMutation | null = null;
      set((state) => {
        const scenario = state.scenarios.find((item) => item.id === scenarioId);
        if (!scenario?.baseScenarioId) return {};
        const nextMutation: ScenarioMutation = {
          id: `mutation-${Date.now()}-${direct.property}`,
          targetId,
          op: "modify" as const,
          kind: "direct" as const,
          description: `${direct.property}: ${direct.previousValue} → ${direct.value}`,
          direct,
          name: name.trim(),
        };
        mutation = nextMutation;
        const scenarios = state.scenarios.map((item) =>
          item.id === scenarioId ? { ...item, mutations: [...item.mutations, nextMutation] } : item,
        );
        saveProjectScenarios(state.currentProjectId, scenarios);
        return {
          scenarios,
          scenarioSelection: { scenarioId, mutationId: nextMutation.id },
        };
      });
      return mutation;
    },
    // Scenarios don't change the record yet (they'll become datarecord
    // layers), so selecting one only changes the selection.
    selectScenario: (scenarioId: string) =>
      set({
        scenarioSelection: { scenarioId, mutationId: null },
        itemDrawer: null,
        isNewScenarioDrawerOpen: false,
        newMutationScenarioId: null,
      }),
    selectMutation: (scenarioId: string, mutationId: string) =>
      set({
        scenarioSelection: { scenarioId, mutationId },
        itemDrawer: null,
        isNewScenarioDrawerOpen: false,
        newMutationScenarioId: null,
      }),

    selectedRunId: null,
    // Route changes and direct selection both leave the result inspector.
    selectRun: (id: string | null) => set({ selectedRunId: id, isResultInspectorOpen: false }),
    selectedInspectionId: null,
    selectInspection: (id: string | null) => set({ selectedInspectionId: id }),
    inspections: [] as InspectionCanvas[],
    inspectionsProjectId: null as string | null,
    loadProjectInspections: (projectId: string) =>
      set({
        inspections: loadProjectInspections(projectId),
        inspectionsProjectId: projectId,
        selectedInspectionId: null,
      }),
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
      inspectionSaveTimeout = setTimeout(
        () => saveProjectInspections(get().currentProjectId, get().inspections),
        400,
      );
    },
    deleteInspection: (id: string) =>
      set((state) => {
        const inspections = state.inspections.filter((inspection) => inspection.id !== id);
        saveProjectInspections(state.currentProjectId, inspections);
        return {
          inspections,
          ...(state.selectedInspectionId === id ? { selectedInspectionId: null } : {}),
          // Don't leave the edit form open on an inspection that no longer exists.
          ...(state.editingInspectionId === id
            ? { isNewInspectionDrawerOpen: false, editingInspectionId: null }
            : {}),
        };
      }),
    isResultInspectorOpen: false,
    openResultInspector: () => set({ isResultInspectorOpen: true }),
    closeResultInspector: () => set({ isResultInspectorOpen: false }),
    runs: INITIAL_RUNS,
    runsProjectId: null as string | null,
    loadProjectRuns: (projectId: string) =>
      set({ runs: loadProjectRuns(projectId), runsProjectId: projectId, selectedRunId: null }),
    isRunTourPlaceholderVisible: false,
    setRunTourPlaceholderVisible: (visible: boolean) =>
      set({ isRunTourPlaceholderVisible: visible }),
    createRun: ({
      name,
      scenarioName,
      playbookId,
      playbookName,
      solverPreset,
      horizon,
    }: CreateRunInput) => {
      const run: Run = {
        id: `run-${Date.now()}`,
        name: name.trim(),
        scenarioName,
        playbookId,
        playbookName,
        status: "planned",
        startedAt: "Not started",
        duration: null,
        solverPreset,
        horizon,
      };
      set((state) => ({
        runs: persisted(state.currentProjectId, [run, ...state.runs]),
        selectedRunId: run.id,
        isNewRunDrawerOpen: false,
        editingRunId: null,
      }));
      return run;
    },
    startRun: (id: string) => {
      const state = get();
      const run = state.runs.find((r) => r.id === id);
      if (!run || run.status !== "planned") return;

      // Runs are dummies until they move to the server: the zoning and solver
      // paths read the browser's project database, which is gone. The run's
      // place in the project (oldest first) decides how it ends: odd ones
      // succeed after 3s, even ones fail after 1.5s.
      const ordinal = state.runs.length - state.runs.findIndex((r) => r.id === id);
      const succeeds = ordinal % 2 === 1;
      const projectId = state.currentProjectId;
      set((s) => ({
        runs: persisted(
          s.currentProjectId,
          s.runs.map((r) =>
            r.id === id && r.status === "planned"
              ? { ...r, status: "running", startedAt: "Just now" }
              : r,
          ),
        ),
      }));
      setTimeout(
        () =>
          set((s) => {
            // Stopped or deleted meanwhile, or the project changed: leave it.
            if (
              s.currentProjectId !== projectId ||
              !s.runs.some((r) => r.id === id && r.status === "running")
            )
              return {};
            return {
              runs: persisted(
                s.currentProjectId,
                s.runs.map((r) =>
                  r.id === id
                    ? {
                        ...r,
                        status: succeeds ? "succeeded" : "failed",
                        duration: succeeds ? "3s" : "1.5s",
                      }
                    : r,
                ),
              ),
            };
          }),
        succeeds ? 3000 : 1500,
      );
    },
    // Dummy — stops the run in the UI without a real solver process behind it.
    stopRun: (id: string) =>
      set((state) => ({
        runs: persisted(
          state.currentProjectId,
          state.runs.map((run) =>
            run.id === id && run.status === "running" ? { ...run, status: "failed" } : run,
          ),
        ),
      })),
    renameRun: (id: string, name: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      set((state) => ({
        runs: persisted(
          state.currentProjectId,
          state.runs.map((run) => (run.id === id ? { ...run, name: trimmed } : run)),
        ),
      }));
    },
    // Refuses in-progress runs (their async solve would write back into a
    // missing run) and runs still referenced by an inspection — RunsPanel
    // disables the UI for it, this just guards the action too.
    deleteRun: (id: string) =>
      set((state) => {
        const run = state.runs.find((r) => r.id === id);
        if (!run || run.status === "running") return {};
        if (state.inspections.some((i) => i.runId === id)) return {};
        return {
          runs: persisted(
            state.currentProjectId,
            state.runs.filter((r) => r.id !== id),
          ),
          ...(state.selectedRunId === id
            ? { selectedRunId: null, isResultInspectorOpen: false }
            : {}),
        };
      }),
    selectedPlaybookId: null,
    selectedPlaybookScenarioId: null,
    selectPlaybook: (playbookId: string, scenarioId: string) =>
      set({ selectedPlaybookId: playbookId, selectedPlaybookScenarioId: scenarioId }),
    updateRunNodeParams: (runId: string, nodeId: string, params: Record<string, string>) =>
      set((state) => ({
        runs: persisted(
          state.currentProjectId,
          state.runs.map((run) =>
            run.id === runId
              ? { ...run, nodeParams: { ...run.nodeParams, [nodeId]: params } }
              : run,
          ),
        ),
      })),
    // Dummy — a real 'patch' promotion would diff the run's resolved model
    // against its base scenario and bake the result into a fresh mutation
    // set; here it just registers an empty-patch scenario so the flow is
    // real end-to-end (it shows up in the Scenarios panel, selectable like
    // any other) even though the diff itself isn't computed yet.
    //
    // Zoning is the one playbook whose promotionStrategy is 'new-scenario'
    // (see src/data/playbooks.ts) — its scenario just pins the zone count the
    // run used (zoningParams). Different zone counts are different scenarios;
    // the same zone count re-promoted is a no-op dedup, not a pile-up.
    promoteRunToScenario: (runId: string) => {
      set((state) => {
        const run = state.runs.find((r) => r.id === runId);
        if (!run || run.status !== "succeeded") return {};
        const isZonalResult = run.playbookId === "playbook-zoning-generation";
        const zoneCount = run.zoningResult?.zoneCount ?? 5;
        const scenarioName = isZonalResult
          ? `Zonal Playbook Result (${zoneCount} zones)`
          : `${run.name ?? run.scenarioName} (Promoted)`;
        if (state.scenarios.some((item) => item.name === scenarioName)) return {};
        const scenario: Scenario = {
          id: `scenario-${Date.now()}`,
          name: scenarioName,
          modelResolution: isZonalResult ? "zonal" : "nodal",
          zoningParams: isZonalResult ? { zoneCount } : undefined,
          mutations: [],
        };
        const scenarios = isZonalResult
          ? [...state.scenarios, scenario]
          : [scenario, ...state.scenarios];
        saveProjectScenarios(state.currentProjectId, scenarios);
        return {
          scenarios,
          scenarioSelection: { scenarioId: scenario.id, mutationId: null },
        };
      });
    },

    reports: [] as Report[],
    reportsProjectId: null as string | null,
    loadProjectReports: (projectId: string) =>
      set({
        reports: loadProjectReports(projectId),
        reportsProjectId: projectId,
        selectedReportId: null,
      }),
    isReportTourPlaceholderVisible: false,
    setReportTourPlaceholderVisible: (visible: boolean) =>
      set({ isReportTourPlaceholderVisible: visible }),
    selectedReportId: null,
    selectReport: (id: string | null) => set({ selectedReportId: id }),
    createReport: ({ name, scenarioName, runId, canvasPreset }: CreateReportInput) => {
      const report: Report = {
        id: `report-${Date.now()}`,
        name: name.trim(),
        scenarioName,
        generatedAt: "Just now",
        widgets: widgetsForCanvasPreset(canvasPreset),
        runId,
        canvasPreset,
      };
      set((state) => ({
        reports: persistedReports(state.currentProjectId, [report, ...state.reports]),
        selectedReportId: report.id,
        isNewReportDrawerOpen: false,
      }));
      return report;
    },
    renameReport: (id: string, name: string) =>
      set((state) => ({
        reports: persistedReports(
          state.currentProjectId,
          state.reports.map((report) =>
            report.id === id ? { ...report, name: name.trim() } : report,
          ),
        ),
        isNewReportDrawerOpen: false,
        editingReportId: null,
      })),
    deleteReport: (id: string) =>
      set((state) => ({
        reports: persistedReports(
          state.currentProjectId,
          state.reports.filter((report) => report.id !== id),
        ),
        // The widget config drawer edits the selected report's widgets, so
        // close it along with the selection.
        ...(state.selectedReportId === id
          ? { selectedReportId: null, isNewWidgetDrawerOpen: false, editingWidgetId: null }
          : {}),
        ...(state.editingReportId === id
          ? { isNewReportDrawerOpen: false, editingReportId: null }
          : {}),
      })),
    addWidgetToReport: (widget: ReportWidget) =>
      set((state) => ({
        reports: persistedReports(
          state.currentProjectId,
          state.reports.map((report) =>
            report.id === state.selectedReportId
              ? { ...report, widgets: [...report.widgets, widget] }
              : report,
          ),
        ),
      })),
    updateWidgetInReport: (widget: ReportWidget) =>
      set((state) => ({
        reports: persistedReports(
          state.currentProjectId,
          state.reports.map((report) =>
            report.id === state.selectedReportId
              ? { ...report, widgets: report.widgets.map((w) => (w.id === widget.id ? widget : w)) }
              : report,
          ),
        ),
      })),
    removeWidgetFromReport: (widgetId: string) =>
      set((state) => ({
        reports: persistedReports(
          state.currentProjectId,
          state.reports.map((report) =>
            report.id === state.selectedReportId
              ? { ...report, widgets: report.widgets.filter((w) => w.id !== widgetId) }
              : report,
          ),
        ),
      })),
  };
}
