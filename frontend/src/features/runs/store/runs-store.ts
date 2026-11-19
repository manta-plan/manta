import { create } from "zustand";
import { buildConfig } from "../../playbook-config/buildConfig";
import { getPlaybook, listPlaybooks, validatePlaybookConfig } from "../../playbooks/api";
import type {
  PlaybookConfig,
  PlaybookDetail,
  PlaybookIssue,
  PlaybookSummary,
} from "../../../utils/playbookTypes";
import {
  createRun,
  getProjectRun,
  getRun,
  getRunLogs,
  getRunSummary,
  listRuns,
} from "../api";
import { describeStepErrors, getStepErrors, toMessage } from "../run-draft";
import { normalizeRunStatus } from "../status";
import { splitStatusFilter } from "../status-groups";
import type {
  DataRecordChoice,
  ExpandedRunState,
  GetRunResponse,
  GetRunSummaryResponse,
  RunDraft,
  RunListItem,
  RunStatus,
} from "../types";

export const runsPageSize = 10;
// A draft's id starts with this, which tells it from a run's UUID in the URL.
export const draftIdPrefix = "draft-";
export const emptyRunSummary: GetRunSummaryResponse = { total: 0, statuses: {} };

export type NewDraftInput = {
  projectId: string;
  playbook: string;
  dataRecord: DataRecordChoice;
  scenarioId: string | null;
  scenarioLabel: string | null;
  config: PlaybookConfig;
  solverPreset: string;
  horizon: string;
};

type LoadStatus = "idle" | "loading" | "ready" | "error";

export type RunsState = {
  /** Who started the runs listed; the backend does not say. */
  /** The project the Run tab is open in; null until init. */
  projectId: string | null;
  owner: string;

  // The backend page: the source of truth for runs. The sidebar, stats and table all read it.
  runs: RunListItem[];
  runsTotal: number;
  runsOffset: number;
  runSummary: GetRunSummaryResponse;
  isRefreshingRuns: boolean;
  runsError: string | null;
  selectedStatuses: RunStatus[];
  /** What the search box holds. */
  searchRunId: string;
  /** The search that is applied; "" for none. */
  activeSearchRunId: string;
  expandedRunId: string | null;
  expandedRuns: Record<string, ExpandedRunState>;
  /** A run opened by its URL that is not on the page loaded; null if the backend has none. */
  lookedUpRun: { id: string; run: RunListItem | null; error: string | null } | null;

  playbooks: PlaybookSummary[];
  playbooksStatus: LoadStatus;
  playbooksError: string | null;
  playbookDetails: Record<string, PlaybookDetail>;
  playbookDetailErrors: Record<string, string>;

  drafts: RunDraft[];
  /** Preselected in the New Run panel: a scenario's name and a playbook's name. */
  selectedScenario: string | null;
  selectedPlaybook: string | null;
  /** Moves on each time the panel opens, so its form starts again. */
  newRunSession: number;

  startingDraftId: string | null;
  startPhase: "validating" | "submitting" | null;
  startError: string | null;
  startIssues: PlaybookIssue[];

  init: (projectId: string, owner: string) => Promise<void>;
  refresh: () => Promise<void>;
  setSelectedStatuses: (statuses: RunStatus[]) => Promise<void>;
  setSearchRunId: (text: string) => void;
  submitSearch: () => Promise<void>;
  clearSearch: () => Promise<void>;
  goToPreviousPage: () => Promise<void>;
  goToNextPage: () => Promise<void>;
  refreshRunDetails: (runId: string) => Promise<void>;
  toggleRunDetails: (runId: string) => Promise<void>;
  lookUpRun: (runId: string) => Promise<void>;

  loadPlaybooks: () => Promise<void>;
  loadPlaybookDetail: (name: string) => Promise<void>;

  prepareNewRun: (selection?: { scenario?: string | null; playbook?: string | null }) => void;
  createDraft: (input: NewDraftInput) => RunDraft;
  setDraftStepConfig: (id: string, stepName: string, value: Record<string, unknown>) => void;
  deleteDraft: (id: string) => void;
  startDraft: (id: string) => Promise<string | null>;
  clearStartError: () => void;
};

export function toRunListItem(run: GetRunResponse, owner: string): RunListItem {
  return {
    id: run.uuid,
    name: run.playbook,
    playbook: run.playbook,
    status: normalizeRunStatus(run.status),
    startedAt: run.created_at,
    durationSeconds: null,
    trigger: "Manual",
    owner,
  };
}

// Each list request takes a number; one that is no longer the latest is ignored, so a slow
// response for an earlier filter or page never replaces a newer one.
let latestListRequest = 0;
// Details being fetched, so a playbook is asked for once however many components want it.
const detailRequests = new Set<string>();

export const useRunsStore = create<RunsState>((set, get) => {
  async function loadPage(project: string, offset: number, selected: RunStatus[]) {
    const request = ++latestListRequest;
    const { serverStatuses, isDraftOnly } = splitStatusFilter(selected);

    set({ isRefreshingRuns: true, runsError: null });

    try {
      if (isDraftOnly) {
        // Drafts are local: nothing of the backend matches, only its totals are needed.
        const summary = await getRunSummary(project);

        if (request === latestListRequest) {
          set({ runs: [], runsTotal: 0, runsOffset: 0, runSummary: summary });
        }

        return;
      }

      const fetched = await listRuns(project, {
        limit: runsPageSize,
        offset,
        statuses: serverStatuses,
      });

      if (request === latestListRequest) {
        const owner = get().owner;

        set({
          runs: fetched.items.map((run) => toRunListItem(run, owner)),
          runsTotal: fetched.total,
          runsOffset: fetched.offset,
          runSummary: fetched.summary,
        });
      }
    } catch (error) {
      if (request === latestListRequest) {
        set({ runsError: toMessage(error, "Failed to refresh runs.") });
      }
    } finally {
      if (request === latestListRequest) {
        set({ isRefreshingRuns: false });
      }
    }
  }

  async function loadSearch(project: string, runId: string) {
    const request = ++latestListRequest;

    set({ isRefreshingRuns: true, runsError: null });

    try {
      const [run, summary] = await Promise.all([
        getProjectRun(project, runId),
        getRunSummary(project),
      ]);

      if (request === latestListRequest) {
        set({
          runs: run === null ? [] : [toRunListItem(run, get().owner)],
          runsTotal: run === null ? 0 : 1,
          runsOffset: 0,
          runSummary: summary,
        });
      }
    } catch (error) {
      if (request === latestListRequest) {
        set({ runsError: toMessage(error, "Failed to search run.") });
      }
    } finally {
      if (request === latestListRequest) {
        set({ isRefreshingRuns: false });
      }
    }
  }

  return {
    projectId: null,
    owner: "",
    runs: [],
    runsTotal: 0,
    runsOffset: 0,
    runSummary: emptyRunSummary,
    isRefreshingRuns: false,
    runsError: null,
    selectedStatuses: [],
    searchRunId: "",
    activeSearchRunId: "",
    expandedRunId: null,
    expandedRuns: {},
    lookedUpRun: null,

    playbooks: [],
    playbooksStatus: "idle",
    playbooksError: null,
    playbookDetails: {},
    playbookDetailErrors: {},

    drafts: [],
    selectedScenario: null,
    selectedPlaybook: null,
    newRunSession: 0,

    startingDraftId: null,
    startPhase: null,
    startError: null,
    startIssues: [],

    init: async (projectId, owner) => {
      set({ projectId, owner });
      await get().refresh();
    },

    refresh: async () => {
      const project = get().projectId;

      if (project === null) {
        return;
      }

      const { activeSearchRunId, runsOffset, selectedStatuses } = get();

      if (activeSearchRunId.length > 0) {
        await loadSearch(project, activeSearchRunId);
        return;
      }

      await loadPage(project, runsOffset, selectedStatuses);
    },

    setSelectedStatuses: async (statuses) => {
      set({ selectedStatuses: statuses, searchRunId: "", activeSearchRunId: "", runsOffset: 0 });

      const project = get().projectId;

      if (project !== null) {
        await loadPage(project, 0, statuses);
      }
    },

    setSearchRunId: (text) => set({ searchRunId: text }),

    submitSearch: async () => {
      const runId = get().searchRunId.trim();
      const project = get().projectId;

      if (project === null) {
        return;
      }

      if (runId.length === 0) {
        set({ activeSearchRunId: "", runsOffset: 0 });
        await loadPage(project, 0, get().selectedStatuses);
        return;
      }

      set({ selectedStatuses: [], activeSearchRunId: runId });
      await loadSearch(project, runId);
    },

    clearSearch: async () => {
      set({ searchRunId: "", activeSearchRunId: "", runsOffset: 0 });

      const project = get().projectId;

      if (project !== null) {
        await loadPage(project, 0, get().selectedStatuses);
      }
    },

    goToPreviousPage: async () => {
      const project = get().projectId;

      if (project !== null) {
        const { runsOffset, selectedStatuses } = get();

        await loadPage(project, Math.max(runsOffset - runsPageSize, 0), selectedStatuses);
      }
    },

    goToNextPage: async () => {
      const project = get().projectId;

      if (project !== null) {
        const { runsOffset, selectedStatuses } = get();

        await loadPage(project, runsOffset + runsPageSize, selectedStatuses);
      }
    },

    refreshRunDetails: async (runId) => {
      const previous = get().expandedRuns[runId];

      set((state) => ({
        expandedRuns: {
          ...state.expandedRuns,
          [runId]: {
            isLoading: true,
            error: null,
            detail: previous?.detail ?? null,
            logs: previous?.logs ?? null,
          },
        },
      }));

      try {
        const projectId = get().projectId;
        const [detail, logs, latestSummary] = await Promise.all([
          getRun(runId),
          getRunLogs(runId),
          projectId === null ? Promise.resolve(null) : getRunSummary(projectId),
        ]);
        const status = normalizeRunStatus(logs.run_status || detail.status);

        set((state) => ({
          runs: state.runs.map((run) =>
            run.id === runId ? { ...run, status, startedAt: detail.created_at } : run,
          ),
          expandedRuns: {
            ...state.expandedRuns,
            [runId]: { isLoading: false, error: null, detail, logs },
          },
          runSummary: latestSummary ?? state.runSummary,
        }));
      } catch (error) {
        set((state) => ({
          expandedRuns: {
            ...state.expandedRuns,
            [runId]: {
              isLoading: false,
              error: toMessage(error, "Failed to load run details."),
              detail: state.expandedRuns[runId]?.detail ?? null,
              logs: state.expandedRuns[runId]?.logs ?? null,
            },
          },
        }));
      }
    },

    toggleRunDetails: async (runId) => {
      if (get().expandedRunId === runId) {
        set({ expandedRunId: null });
        return;
      }

      set({ expandedRunId: runId });

      const expanded = get().expandedRuns[runId];

      if (expanded !== undefined && expanded.detail !== null && expanded.logs !== null) {
        return;
      }

      await get().refreshRunDetails(runId);
    },

    lookUpRun: async (runId) => {
      const project = get().projectId;

      if (project === null) {
        set({ lookedUpRun: { id: runId, run: null, error: "No project to look the run up in." } });
        return;
      }

      try {
        const run = await getProjectRun(project, runId);

        set({
          lookedUpRun: {
            id: runId,
            run: run === null ? null : toRunListItem(run, get().owner),
            error: null,
          },
        });
      } catch (error) {
        set({
          lookedUpRun: { id: runId, run: null, error: toMessage(error, "Failed to load run.") },
        });
      }
    },

    loadPlaybooks: async () => {
      if (get().playbooksStatus === "loading" || get().playbooksStatus === "ready") {
        return;
      }

      set({ playbooksStatus: "loading", playbooksError: null });

      try {
        const response = await listPlaybooks();

        set({ playbooks: response.items, playbooksStatus: "ready" });
      } catch (error) {
        set({
          playbooksStatus: "error",
          playbooksError: toMessage(error, "Failed to load playbooks."),
        });
      }
    },

    loadPlaybookDetail: async (name) => {
      if (get().playbookDetails[name] !== undefined || detailRequests.has(name)) {
        return;
      }

      detailRequests.add(name);

      set((state) => {
        const { [name]: _cleared, ...errors } = state.playbookDetailErrors;

        return { playbookDetailErrors: errors };
      });

      try {
        const detail = await getPlaybook(name);

        set((state) => ({ playbookDetails: { ...state.playbookDetails, [name]: detail } }));
      } catch (error) {
        set((state) => ({
          playbookDetailErrors: {
            ...state.playbookDetailErrors,
            [name]: toMessage(error, "Failed to load playbook."),
          },
        }));
      } finally {
        detailRequests.delete(name);
      }
    },

    prepareNewRun: (selection) =>
      set((state) => ({
        selectedScenario: selection?.scenario ?? null,
        selectedPlaybook: selection?.playbook ?? null,
        newRunSession: state.newRunSession + 1,
      })),

    createDraft: (input) => {
      const draft: RunDraft = {
        ...input,
        id: `${draftIdPrefix}${crypto.randomUUID()}`,
        config: structuredClone(input.config),
        createdAt: new Date().toISOString(),
      };

      set((state) => ({ drafts: [draft, ...state.drafts] }));

      return draft;
    },

    setDraftStepConfig: (id, stepName, value) =>
      set((state) => ({
        drafts: state.drafts.map((draft) =>
          // A new config object: Start compares it to tell a draft edited while it checked.
          draft.id === id ? { ...draft, config: { ...draft.config, [stepName]: value } } : draft,
        ),
        startError: null,
        startIssues: [],
      })),

    deleteDraft: (id) =>
      set((state) => ({ drafts: state.drafts.filter((draft) => draft.id !== id) })),

    startDraft: async (id) => {
      const draft = get().drafts.find((item) => item.id === id);

      if (draft === undefined || get().startingDraftId !== null) {
        return null;
      }

      const detail = get().playbookDetails[draft.playbook];

      if (detail === undefined) {
        set({
          startError: "The playbook is still loading. Try again in a moment.",
          startIssues: [],
        });
        return null;
      }

      const stepError = describeStepErrors(getStepErrors(detail, draft.config));

      if (stepError !== null) {
        set({ startError: stepError, startIssues: [] });
        return null;
      }

      set({ startingDraftId: id, startPhase: "validating", startError: null, startIssues: [] });

      // Values are taken before the first await and used after it.
      const config = buildConfig(detail, draft.config);

      try {
        // The backend's own check, so every problem is shown here instead of the run being
        // refused afterwards.
        try {
          const result = await validatePlaybookConfig(draft.playbook, config);
          const current = get().drafts.find((item) => item.id === id);

          // Deleted or edited while it was checked: that check says nothing of this draft.
          if (current === undefined || current.config !== draft.config) {
            return null;
          }

          if (!result.valid) {
            set({
              startError:
                "This configuration cannot be run yet. Please resolve the following issues:",
              startIssues: result.issues,
            });
            return null;
          }
        } catch (error) {
          set({
            startError: toMessage(error, "Unable to validate the configuration. Please try again."),
          });
          return null;
        }

        set({ startPhase: "submitting" });

        let created: Awaited<ReturnType<typeof createRun>>;

        try {
          created = await createRun(draft.projectId, {
            playbook: draft.playbook,
            config,
            dataRecord: draft.dataRecord,
          });
        } catch (error) {
          set({ startError: toMessage(error, "Failed to create run.") });
          return null;
        }

        set((state) => ({
          drafts: state.drafts.filter((item) => item.id !== id),
          searchRunId: "",
          activeSearchRunId: "",
          runsOffset: 0,
        }));
        await loadPage(draft.projectId, 0, get().selectedStatuses);

        return created.uuid;
      } finally {
        set({ startingDraftId: null, startPhase: null });
      }
    },

    clearStartError: () => set({ startError: null, startIssues: [] }),
  };
});
