import type { InspectionCanvas, InspectionContent } from "../../analyse/data/inspections";
import type { PageSetup, Report, ReportBlock, ReportPage } from "../../analyse/data/reports";
import type { ReportTheme } from "../../analyse/data/report-themes";
import type { EditOptions, ReportHistories } from "../../analyse/lib/report-history";
import type { ConnectionStatus } from "../lib/record-server/client";
import type {
  Carrier,
  EntityCount,
  Location,
  LocationZone,
  RecordInfo,
  ScenarioChangeSummary,
  ScenarioChangeValue,
} from "../lib/record-server/types";
import type { Run } from "../data/runs";
import type {
  Scenario,
  ScenarioDirectChange,
  ScenarioMutation,
  ScenarioRule,
} from "../data/scenarios";
import type {
  ChangeDialogSeed,
  DraftChangeInput,
  DraftScenario,
  EntityDialogSeed,
} from "../lib/draft-scenarios";

export type { Run } from "../data/runs";
export type { Scenario } from "../data/scenarios";

export type { InspectionCanvas } from "../../analyse/data/inspections";
export type { Report } from "../../analyse/data/reports";

export type ToolId = "select" | "identify" | "measure-distance" | "measure-area";

// The two vector basemaps follow the UI theme; satellite imagery has no
// light/dark variant, so it stays put when the theme toggles.
export type BasemapId = "vector-dark" | "vector-light" | "satellite";

// What a session loads once from the record server; the tree's entities and
// an item's attributes are fetched on demand instead.
export interface LoadedRecord {
  info: RecordInfo;
  carriers: Record<string, Carrier>;
  entityCounts: EntityCount[];
  locations: Location[];
  zones: LocationZone[];
  // Per scenario, the attributes it changes.
  scenarioChanges: ScenarioChangeSummary[];
  // The scenario shown (a revision name; null for a plain record), and the
  // values it changes against its parent, by changeKey. Everything above but
  // info and scenarioChanges is this scenario's.
  scenario: string | null;
  changes: Map<string, ScenarioChangeValue>;
}

export type UtilityDrawerFlow = "ai-chat" | "share";

export interface ScenarioSelection {
  scenarioId: string;
  mutationId: string | null;
}

export interface CreateRunInput {
  name: string;
  scenarioName: string;
  playbookId: string;
  playbookName: string;
  solverPreset: string;
  horizon: string;
}

export interface CreateReportInput {
  name: string;
  page: PageSetup;
  theme: ReportTheme;
  /** What the report starts with; one empty page when left out. */
  pages?: ReportPage[];
}

export interface CreateInspectionInput {
  name: string;
  description: string;
}

/** A new inspection also takes the page it starts from. */
export type NewInspectionInput = CreateInspectionInput & InspectionContent;

export interface CreateScenarioInput {
  name: string;
  baseScenarioId?: string;
  baseModelSourceIds?: string[];
}

export interface CreateScenarioMutationInput {
  scenarioId: string;
  name: string;
  targetId: string;
  rule: ScenarioRule;
}

export interface CreateScenarioDirectMutationInput {
  scenarioId: string;
  name: string;
  targetId: string;
  direct: ScenarioDirectChange;
}

export interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  bearing: number;
  pitch: number;
}

export interface CursorPosition {
  lng: number;
  lat: number;
}

export interface ProjectState {
  currentProjectId: string | null;
  setCurrentProjectId: (id: string) => void;
  isWelcomeDialogOpen: boolean;
  openWelcomeDialog: () => void;
  closeWelcomeDialog: () => void;

  activeTool: ToolId;
  setActiveTool: (tool: ToolId) => void;

  basemap: BasemapId;
  setBasemap: (basemap: BasemapId) => void;

  utilityDrawerFlow: UtilityDrawerFlow | null;
  toggleUtilityDrawer: (flow: UtilityDrawerFlow) => void;
  closeUtilityDrawer: () => void;

  /** Closes the tab-specific drawers (the scenario change table, the inner right stack) on project tab changes. */
  closePageDrawers: () => void;

  configuringRunNodeId: string | null;
  openRunNodeConfigDrawer: (nodeId: string) => void;
  closeRunNodeConfigDrawer: () => void;
  updateRunNodeParams: (runId: string, nodeId: string, params: Record<string, string>) => void;

  isRunFilterDrawerOpen: boolean;
  openRunFilterDrawer: () => void;
  closeRunFilterDrawer: () => void;

  // The attribute whose changes the bottom drawer shows (a Scenarios panel change row).
  scenarioChange: { scenario: string; attribute: string } | null;
  openScenarioChange: (scenario: string, attribute: string) => void;
  closeScenarioChange: () => void;

  isNewScenarioDrawerOpen: boolean;
  editingScenarioId: string | null;
  openNewScenarioDrawer: () => void;
  openEditScenarioDrawer: (scenarioId: string) => void;
  closeNewScenarioDrawer: () => void;
  renameScenario: (id: string, name: string) => void;
  deleteScenario: (id: string) => void;
  newMutationScenarioId: string | null;
  openNewMutationDrawer: (scenarioId: string) => void;
  closeNewMutationDrawer: () => void;

  // The link to the record server, kept up to date by the client's checks.
  connectionStatus: ConnectionStatus;
  reconnect: () => void;

  record: LoadedRecord | null;
  recordStatus: "idle" | "loading" | "ready" | "error";
  recordError: string | null;
  // The record asked for: a project's recordId, or null for the server's
  // default; undefined before any.
  recordRequest: string | null | undefined;
  loadRecord: (id: string | null) => void;
  // Shows another scenario: the record's per-scenario parts reload, and the
  // tree, drawers and map follow. The one being loaded, until it's shown.
  switchingScenario: string | null;
  showScenario: (name: string) => void;

  scenarios: Scenario[];
  scenarioSelection: ScenarioSelection;
  loadProjectScenarios: (projectId: string) => void;
  createScenario: (input: CreateScenarioInput) => Scenario;
  createScenarioMutation: (input: CreateScenarioMutationInput) => ScenarioMutation | null;
  createScenarioDirectMutation: (
    input: CreateScenarioDirectMutationInput,
  ) => ScenarioMutation | null;
  selectScenario: (scenarioId: string) => void;
  selectMutation: (scenarioId: string, mutationId: string) => void;

  selectedRunId: string | null;
  selectRun: (id: string | null) => void;
  selectedInspectionId: string | null;
  selectInspection: (id: string | null) => void;
  isResultInspectorOpen: boolean;
  openResultInspector: () => void;
  closeResultInspector: () => void;
  promoteRunToScenario: (runId: string) => void;
  runs: Run[];
  /** Project whose runs are in `runs`; null until the first load. */
  runsProjectId: string | null;
  loadProjectRuns: (projectId: string) => void;
  // Shows a non-interactive example row in RunsPanel so the Run tour has
  // something to highlight when the project genuinely has zero runs — see
  // src/lib/workspaceTours.ts's startRunWorkspaceTour.
  isRunTourPlaceholderVisible: boolean;
  setRunTourPlaceholderVisible: (visible: boolean) => void;
  isNewRunDrawerOpen: boolean;
  editingRunId: string | null;
  openNewRunDrawer: () => void;
  openEditRunDrawer: (runId: string) => void;
  closeNewRunDrawer: () => void;
  createRun: (input: CreateRunInput) => Run;
  startRun: (id: string) => void;
  stopRun: (id: string) => void;
  renameRun: (id: string, name: string) => void;
  deleteRun: (id: string) => void;
  selectedPlaybookId: string | null;
  selectedPlaybookScenarioId: string | null;
  selectPlaybook: (playbookId: string, scenarioId: string) => void;

  // The Analyse tab: views (inspections) and reports, saved per project.
  // The view or report open on the Analyse tab; selectedInspectionId is only a type or entity page on Inspect.
  selectedViewId: string | null;
  selectView: (id: string | null) => void;
  reports: Report[];
  /** Project whose reports are in `reports`; null until the first load. */
  reportsProjectId: string | null;
  updateReport: (id: string, patch: { name: string; page: PageSetup }) => void;
  updateReportBlocks: (
    reportId: string,
    pageId: string,
    update: (blocks: ReportBlock[]) => ReportBlock[],
    options?: EditOptions,
  ) => void;
  /** Undo and redo steps per open report, in memory. */
  reportHistory: ReportHistories;
  undoReport: (reportId: string) => void;
  redoReport: (reportId: string) => void;
  setReportTheme: (reportId: string, theme: ReportTheme) => void;
  addReportPage: (reportId: string) => void;
  removeReportPage: (reportId: string, pageId: string) => void;
  deleteReport: (id: string) => void;
  /** Takes the views and reports another tab saved. */
  refreshFromStorage: () => void;
  loadProjectReports: (projectId: string) => void;
  selectedReportId: string | null;
  selectReport: (id: string | null) => void;
  isNewReportDrawerOpen: boolean;
  openNewReportDrawer: () => void;
  /** Report being edited in the New Report drawer; null when creating. */
  editingReportId: string | null;
  openEditReportDrawer: (reportId: string) => void;
  closeNewReportDrawer: () => void;
  createReport: (input: CreateReportInput) => Report;

  inspections: InspectionCanvas[];
  /** Project whose inspections are in `inspections`; null until the first load. */
  inspectionsProjectId: string | null;
  loadProjectInspections: (projectId: string) => void;
  createInspection: (input: NewInspectionInput) => InspectionCanvas;
  updateInspection: (id: string, input: CreateInspectionInput) => void;
  /** Saves what an inspection's page holds: its widgets, result, comparison and filters. */
  updateInspectionContent: (id: string, content: Partial<InspectionContent>) => void;
  deleteInspection: (id: string) => void;
  isNewInspectionDrawerOpen: boolean;
  openNewInspectionDrawer: () => void;
  /** Inspection being edited in the New Inspection drawer; null when creating. */
  editingInspectionId: string | null;
  openEditInspectionDrawer: (inspectionId: string) => void;
  closeNewInspectionDrawer: () => void;

  viewState: ViewState;
  setViewState: (v: ViewState) => void;
  // A request for the map to show these [longitude, latitude] points; `at`
  // makes asking twice for the same points move the map again.
  mapFocus: { points: [number, number][]; at: number } | null;
  focusMap: (points: [number, number][]) => void;

  cursorPosition: CursorPosition | null;
  setCursorPosition: (c: CursorPosition | null) => void;

  // Draft scenarios, made on the Build tab and kept in the browser (see
  // lib/draft-scenarios and slices/draft-slice).
  draftScenarios: DraftScenario[];
  loadProjectDrafts: (projectId: string) => void;
  createDraft: (input: {
    recordId: string;
    parent: string;
    name: string;
    description: string;
  }) => DraftScenario;
  updateDraft: (id: string, patch: { name?: string; description?: string }) => void;
  deleteDraft: (id: string) => void;
  saveDraftChange: (draftId: string, change: DraftChangeInput) => void;
  removeDraftChange: (draftId: string, changeId: string) => void;
  // The draft the Build tab shows (over its parent, which the record shows).
  shownDraftId: string | null;
  showDraft: (id: string) => void;
  scenarioDialog: { mode: "new" } | { mode: "edit"; draftId: string } | null;
  openScenarioDialog: (dialog: { mode: "new" } | { mode: "edit"; draftId: string }) => void;
  closeScenarioDialog: () => void;
  changeDialog: ChangeDialogSeed | null;
  openChangeDialog: (seed: ChangeDialogSeed) => void;
  closeChangeDialog: () => void;
  entityDialog: EntityDialogSeed | null;
  openEntityDialog: (seed: EntityDialogSeed) => void;
  closeEntityDialog: () => void;
}

export type ProjectStoreSet = (
  partial: Partial<ProjectState> | ((state: ProjectState) => Partial<ProjectState>),
) => void;
export type ProjectStoreGet = () => ProjectState;
