import type { InspectionCanvas } from "../data/inspections";
import type { InspectionContent } from "../data/inspections";
import type { MapLayerStyle } from "../data/map-layers";
import type { ConnectionStatus } from "../lib/record-server/client";
import type {
  Branch,
  Carrier,
  EntityCount,
  Location,
  LocationZone,
  RecordInfo,
  Region,
  ScenarioChangeSummary,
  ScenarioChangeValue,
} from "../lib/record-server/types";
import type { Report, ReportCanvasPreset } from "../data/reports";
import type { ReportWidget } from "../data/report-widgets";
import type { Run, RunStatus } from "../data/runs";
import type {
  Scenario,
  ScenarioDirectChange,
  ScenarioMutation,
  ScenarioRule,
} from "../data/scenarios";

export type { InspectionCanvas } from "../data/inspections";
export type { Report } from "../data/reports";
export type { ReportCanvasPreset } from "../data/reports";
export type { ReportWidget } from "../data/report-widgets";
export type { Run } from "../data/runs";
export type { Scenario } from "../data/scenarios";

export type ToolId = "select" | "identify" | "measure-distance" | "measure-area";

// The two vector basemaps follow the UI theme; satellite imagery has no
// light/dark variant, so it stays put when the theme toggles.
export type BasemapId = "vector-dark" | "vector-light" | "satellite";

// 'nodal' (the record as is), or a zone level: a busmap_* attribute name.
export type Resolution = string;
export const NODAL: Resolution = "nodal";

// What a session loads once from the record server; the tree's entities and
// an item's attributes are fetched on demand instead.
export interface LoadedRecord {
  info: RecordInfo;
  carriers: Record<string, Carrier>;
  entityCounts: EntityCount[];
  locations: Location[];
  zones: LocationZone[];
  // Branches between two real locations: what the map draws.
  branches: Branch[];
  regions: Region[];
  // Per scenario, the attributes it changes.
  scenarioChanges: ScenarioChangeSummary[];
  // The scenario shown (a revision name; null for a plain record), and the
  // values it changes against its parent, by changeKey. Everything above but
  // info and scenarioChanges is this scenario's.
  scenario: string | null;
  changes: Map<string, ScenarioChangeValue>;
}

// Something the tree, map or drawers point at.
export type RecordItem =
  | { kind: "entity"; entity: string; ctype: string; carrier: string | null; locations: string[] }
  // `name` is how the label reads, where its text isn't readable (a struct).
  | { kind: "label"; dim: string; label: string; name?: string };

export type TableDrawerContent =
  // A Data Catalogue file's placeholder table.
  | { kind: "catalog"; title: string }
  | { kind: "entities"; ctype: string; carrier: string | null }
  | { kind: "series"; entity: string; attribute: string; bus: string | null }
  // One location, or a zone's locations.
  | { kind: "location"; title: string; locations: string[] }
  // One attribute a scenario changes, per entity or bus.
  | { kind: "scenario-change"; scenario: string; attribute: string };

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
  scenarioName: string;
  runId?: string;
  canvasPreset: ReportCanvasPreset;
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

  // Overrides only: a layer without an entry shows its default (see mapLayers.ts).
  mapLayerVisibility: Record<string, boolean>;
  setMapLayerVisible: (id: string, visible: boolean) => void;

  mapLayerStyle: Record<string, Partial<MapLayerStyle>>;
  setMapLayerColor: (id: string, color: string) => void;
  setMapLayerOpacity: (id: string, opacity: number) => void;
  resetMapLayerStyle: (id: string) => void;

  utilityDrawerFlow: UtilityDrawerFlow | null;
  toggleUtilityDrawer: (flow: UtilityDrawerFlow) => void;
  closeUtilityDrawer: () => void;

  isMapLayersDrawerOpen: boolean;
  toggleMapLayersDrawer: () => void;
  /** Closes the tab-specific drawers (bottom table, inner right stack) on project tab changes. */
  closePageDrawers: () => void;

  isNewWidgetDrawerOpen: boolean;
  editingWidgetId: string | null;
  toggleNewWidgetDrawer: () => void;
  openWidgetConfigDrawer: (widgetId: string) => void;
  closeNewWidgetDrawer: () => void;

  configuringRunNodeId: string | null;
  openRunNodeConfigDrawer: (nodeId: string) => void;
  closeRunNodeConfigDrawer: () => void;
  updateRunNodeParams: (runId: string, nodeId: string, params: Record<string, string>) => void;

  isRunFilterDrawerOpen: boolean;
  runStatusFilters: RunStatus[];
  openRunFilterDrawer: () => void;
  closeRunFilterDrawer: () => void;
  toggleRunStatusFilter: (status: RunStatus) => void;
  clearRunFilters: () => void;

  isInspectionFilterDrawerOpen: boolean;
  inspectionFilters: string[];
  openInspectionFilterDrawer: () => void;
  closeInspectionFilterDrawer: () => void;
  toggleInspectionFilter: (filter: string) => void;
  clearInspectionFilters: () => void;

  isReportFilterDrawerOpen: boolean;
  reportFilters: string[];
  openReportFilterDrawer: () => void;
  closeReportFilterDrawer: () => void;
  toggleReportFilter: (filter: string) => void;
  clearReportFilters: () => void;

  tableDrawer: TableDrawerContent | null;
  openTableDrawer: (title: string) => void;
  openEntityTable: (ctype: string, carrier: string | null) => void;
  openSeriesChart: (entity: string, attribute: string, bus: string | null) => void;
  openScenarioChange: (scenario: string, attribute: string) => void;
  openLocationView: (title: string, locations: string[]) => void;
  closeTableDrawer: () => void;
  selectedMapLayerId: string | null;
  selectMapLayer: (id: string) => void;

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

  resolution: Resolution;
  setResolution: (resolution: Resolution) => void;

  // Highlighted in the tree and on the map.
  selectedItem: RecordItem | null;
  selectItem: (item: RecordItem | null) => void;
  // Shown in the item drawer beside the sidebar.
  itemDrawer: RecordItem | null;
  openItemDrawer: (item: RecordItem) => void;
  closeItemDrawer: () => void;

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

  reports: Report[];
  /** Project whose reports are in `reports`; null until the first load. */
  reportsProjectId: string | null;
  renameReport: (id: string, name: string) => void;
  deleteReport: (id: string) => void;
  loadProjectReports: (projectId: string) => void;
  isReportTourPlaceholderVisible: boolean;
  setReportTourPlaceholderVisible: (visible: boolean) => void;
  selectedReportId: string | null;
  selectReport: (id: string | null) => void;
  isNewReportDrawerOpen: boolean;
  /** Pass a dummy run result's id to prefill the form with it. */
  openNewReportDrawer: (resultId?: string) => void;
  newReportResultId: string | null;
  /** Report being edited in the New Report drawer; null when creating. */
  editingReportId: string | null;
  openEditReportDrawer: (reportId: string) => void;
  closeNewReportDrawer: () => void;
  createReport: (input: CreateReportInput) => Report;
  addWidgetToReport: (widget: ReportWidget) => void;
  updateWidgetInReport: (widget: ReportWidget) => void;
  removeWidgetFromReport: (widgetId: string) => void;

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
}

export type ProjectStoreSet = (
  partial: Partial<ProjectState> | ((state: ProjectState) => Partial<ProjectState>),
) => void;
export type ProjectStoreGet = () => ProjectState;
