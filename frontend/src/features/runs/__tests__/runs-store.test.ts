import { beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "../../playbook-config/__fixtures__/cluster-expand-dispatch.json";
import type { PlaybookDetail } from "../../../utils/playbookTypes";
import type { GetRunResponse, ListRunsResponse } from "../types";

vi.mock("../api", () => ({
  createRun: vi.fn(),
  getProjectRun: vi.fn(),
  getRun: vi.fn(),
  getRunLogs: vi.fn(),
  getRunSummary: vi.fn(),
  listRuns: vi.fn(),
}));
vi.mock("../../playbooks/api", () => ({
  getPlaybook: vi.fn(),
  listPlaybooks: vi.fn(),
  validatePlaybookConfig: vi.fn(),
}));

import * as runsApi from "../api";
import * as playbooksApi from "../../playbooks/api";
import { runsPageSize, useRunsStore } from "../store/runs-store";

const playbook = fixture as unknown as PlaybookDetail;
const project = "project-1";
const dataRecord = { name: "ac-dc-meshed", revision_uuid: "rev-1" };

function run(uuid: string, status = "COMPLETED"): GetRunResponse {
  return {
    uuid,
    project_uuid: project,
    playbook: "cluster-expand-dispatch",
    status,
    created_at: "2026-11-01T10:00:00Z",
  };
}

function page(
  items: GetRunResponse[],
  overrides: Partial<ListRunsResponse> = {},
): ListRunsResponse {
  return {
    items,
    total: items.length,
    limit: runsPageSize,
    offset: 0,
    summary: { total: items.length, statuses: { COMPLETED: items.length } },
    ...overrides,
  };
}

const initialState = useRunsStore.getState();

function newDraft(config = playbook.default_config) {
  return useRunsStore.getState().createDraft({
    projectId: project,
    playbook: playbook.name,
    dataRecord,
    scenarioId: "scenario-a",
    scenarioLabel: "Scenario A",
    config,
    solverPreset: "Balanced",
    horizon: "Full year",
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  useRunsStore.setState({ ...initialState, projectId: project }, true);
  vi.mocked(runsApi.getRunSummary).mockResolvedValue({ total: 0, statuses: {} });
});

describe("loading runs", () => {
  it("loads the first page for the owner", async () => {
    vi.mocked(runsApi.listRuns).mockResolvedValue(page([run("a"), run("b")]));

    await useRunsStore.getState().init(project, "ada");

    const state = useRunsStore.getState();
    expect(state.runs.map((item) => item.id)).toEqual(["a", "b"]);
    expect(state.runs[0].owner).toBe("ada");
    expect(state.runsTotal).toBe(2);
    expect(state.isRefreshingRuns).toBe(false);
    expect(state.runsError).toBeNull();
  });

  it("does nothing before a project is set", async () => {
    useRunsStore.setState({ projectId: null });
    await useRunsStore.getState().refresh();

    expect(runsApi.listRuns).not.toHaveBeenCalled();
  });

  it("reports a failed load", async () => {
    vi.mocked(runsApi.listRuns).mockRejectedValue(new Error("backend down"));

    await useRunsStore.getState().refresh();

    expect(useRunsStore.getState().runsError).toBe("Backend down");
    expect(useRunsStore.getState().isRefreshingRuns).toBe(false);
  });

  it("ignores a slow response that a newer request has passed", async () => {
    let resolveSlow: (value: ListRunsResponse) => void = () => {};
    vi.mocked(runsApi.listRuns)
      .mockReturnValueOnce(new Promise((resolve) => (resolveSlow = resolve)))
      .mockResolvedValueOnce(page([run("new")]));

    const slow = useRunsStore.getState().refresh();
    await useRunsStore.getState().setSelectedStatuses(["FAILED"]);
    resolveSlow(page([run("old")]));
    await slow;

    expect(useRunsStore.getState().runs.map((item) => item.id)).toEqual(["new"]);
    expect(useRunsStore.getState().isRefreshingRuns).toBe(false);
  });
});

describe("filtering", () => {
  it("asks the backend for the selected states, back on the first page and without a search", async () => {
    vi.mocked(runsApi.listRuns).mockResolvedValue(page([run("a", "FAILED")]));
    useRunsStore.setState({ runsOffset: 20, searchRunId: "x", activeSearchRunId: "x" });

    await useRunsStore.getState().setSelectedStatuses(["FAILED", "CRASHED"]);

    expect(runsApi.listRuns).toHaveBeenCalledWith(project, {
      limit: runsPageSize,
      offset: 0,
      statuses: ["FAILED", "CRASHED"],
    });
    expect(useRunsStore.getState().activeSearchRunId).toBe("");
    expect(useRunsStore.getState().searchRunId).toBe("");
  });

  it("never sends Draft to the backend", async () => {
    vi.mocked(runsApi.listRuns).mockResolvedValue(page([run("a", "RUNNING")]));

    await useRunsStore.getState().setSelectedStatuses(["DRAFT", "RUNNING"]);

    expect(vi.mocked(runsApi.listRuns).mock.calls[0][1].statuses).toEqual(["RUNNING"]);
  });

  it("does not list backend runs when only Draft is selected", async () => {
    useRunsStore.setState({ runs: [], runsTotal: 3 });
    vi.mocked(runsApi.getRunSummary).mockResolvedValue({ total: 3, statuses: { COMPLETED: 3 } });

    await useRunsStore.getState().setSelectedStatuses(["DRAFT"]);

    expect(runsApi.listRuns).not.toHaveBeenCalled();
    expect(useRunsStore.getState().runs).toEqual([]);
    expect(useRunsStore.getState().runSummary.total).toBe(3);
  });
});

describe("searching", () => {
  it("looks a run up by its UUID and clears the status filter", async () => {
    vi.mocked(runsApi.getProjectRun).mockResolvedValue(run("abc"));
    useRunsStore.setState({ selectedStatuses: ["FAILED"], searchRunId: "  abc " });

    await useRunsStore.getState().submitSearch();

    const state = useRunsStore.getState();
    expect(runsApi.getProjectRun).toHaveBeenCalledWith(project, "abc");
    expect(state.selectedStatuses).toEqual([]);
    expect(state.activeSearchRunId).toBe("abc");
    expect(state.runs.map((item) => item.id)).toEqual(["abc"]);
  });

  it("shows no run when the UUID is unknown", async () => {
    vi.mocked(runsApi.getProjectRun).mockResolvedValue(null);
    useRunsStore.setState({ searchRunId: "nope" });

    await useRunsStore.getState().submitSearch();

    expect(useRunsStore.getState().runs).toEqual([]);
    expect(useRunsStore.getState().runsTotal).toBe(0);
  });

  it("returns to the list when the search is empty", async () => {
    vi.mocked(runsApi.listRuns).mockResolvedValue(page([run("a")]));
    useRunsStore.setState({ searchRunId: "  ", activeSearchRunId: "old" });

    await useRunsStore.getState().submitSearch();

    expect(useRunsStore.getState().activeSearchRunId).toBe("");
    expect(runsApi.listRuns).toHaveBeenCalled();
  });
});

describe("paging", () => {
  it("moves by one page and not below the first", async () => {
    vi.mocked(runsApi.listRuns).mockResolvedValue(page([run("a")], { offset: 10, total: 25 }));
    useRunsStore.setState({ runsOffset: 5 });

    await useRunsStore.getState().goToNextPage();
    expect(vi.mocked(runsApi.listRuns).mock.calls[0][1].offset).toBe(5 + runsPageSize);

    await useRunsStore.getState().goToPreviousPage();
    expect(vi.mocked(runsApi.listRuns).mock.calls[1][1].offset).toBe(0);
  });
});

describe("drafts", () => {
  it("creates a draft with a copy of the config, newest first", () => {
    const first = newDraft();
    const second = newDraft();

    expect(useRunsStore.getState().drafts.map((draft) => draft.id)).toEqual([second.id, first.id]);
    expect(first.config).toEqual(playbook.default_config);
    expect(first.config).not.toBe(playbook.default_config);
    expect(first.scenarioLabel).toBe("Scenario A");
  });

  it("edits one step without touching the others, with a new config object", () => {
    const draft = newDraft();

    useRunsStore.getState().setDraftStepConfig(draft.id, "cluster", { segments: 12 });

    const edited = useRunsStore.getState().drafts[0];
    expect(edited.config.cluster).toEqual({ segments: 12 });
    expect(edited.config.dispatch).toEqual(draft.config.dispatch);
    expect(edited.config).not.toBe(draft.config);
  });

  it("deletes a draft", () => {
    const draft = newDraft();

    useRunsStore.getState().deleteDraft(draft.id);

    expect(useRunsStore.getState().drafts).toEqual([]);
  });
});

describe("startDraft", () => {
  function ready() {
    useRunsStore.setState({ playbookDetails: { [playbook.name]: playbook } });
    vi.mocked(playbooksApi.validatePlaybookConfig).mockResolvedValue({ valid: true, issues: [] });
    vi.mocked(runsApi.createRun).mockResolvedValue({
      uuid: "run-1",
      project_uuid: project,
      created_at: "2026-11-01T10:00:00Z",
    });
    vi.mocked(runsApi.listRuns).mockResolvedValue(page([run("run-1", "SCHEDULED")]));
  }

  it("sends the same payload as before, removes the draft and refreshes the list", async () => {
    ready();
    const draft = newDraft();

    const uuid = await useRunsStore.getState().startDraft(draft.id);

    expect(uuid).toBe("run-1");
    expect(runsApi.createRun).toHaveBeenCalledWith(project, {
      playbook: playbook.name,
      config: playbook.default_config,
      dataRecord,
    });
    expect(useRunsStore.getState().drafts).toEqual([]);
    expect(useRunsStore.getState().runs.map((item) => item.id)).toEqual(["run-1"]);
    expect(useRunsStore.getState().startingDraftId).toBeNull();
  });

  it("keeps the draft when the backend refuses the run", async () => {
    ready();
    vi.mocked(runsApi.createRun).mockRejectedValue(new Error("revision missing"));
    const draft = newDraft();

    const uuid = await useRunsStore.getState().startDraft(draft.id);

    expect(uuid).toBeNull();
    expect(useRunsStore.getState().drafts).toHaveLength(1);
    expect(useRunsStore.getState().startError).toBe("Revision missing");
    expect(useRunsStore.getState().startingDraftId).toBeNull();
  });

  it("does not send a draft with a step error", async () => {
    ready();
    const draft = newDraft({ ...playbook.default_config, cluster: { n_hours: 2.5 } });

    expect(await useRunsStore.getState().startDraft(draft.id)).toBeNull();

    expect(playbooksApi.validatePlaybookConfig).not.toHaveBeenCalled();
    expect(runsApi.createRun).not.toHaveBeenCalled();
    expect(useRunsStore.getState().startError).toBe(
      "Resolve the settings of Cluster before starting the run.",
    );
  });

  it("shows the issues the backend's check finds and does not create the run", async () => {
    ready();
    const issues = [
      { kind: "x", message: "bad", step_path: ["cluster"], config_path: null, input: null },
    ];
    vi.mocked(playbooksApi.validatePlaybookConfig).mockResolvedValue({ valid: false, issues });
    const draft = newDraft();

    expect(await useRunsStore.getState().startDraft(draft.id)).toBeNull();

    expect(runsApi.createRun).not.toHaveBeenCalled();
    expect(useRunsStore.getState().startIssues).toEqual(issues);
    expect(useRunsStore.getState().drafts).toHaveLength(1);
  });

  it("does not create the run when the draft was edited while it was checked", async () => {
    ready();
    const draft = newDraft();
    vi.mocked(playbooksApi.validatePlaybookConfig).mockImplementation(async () => {
      useRunsStore.getState().setDraftStepConfig(draft.id, "cluster", { segments: 12 });
      return { valid: true, issues: [] };
    });

    expect(await useRunsStore.getState().startDraft(draft.id)).toBeNull();

    expect(runsApi.createRun).not.toHaveBeenCalled();
    expect(useRunsStore.getState().startingDraftId).toBeNull();
  });

  it("waits for the playbook", async () => {
    const draft = newDraft();

    expect(await useRunsStore.getState().startDraft(draft.id)).toBeNull();

    expect(useRunsStore.getState().startError).toMatch(/still loading/);
  });
});

describe("playbooks", () => {
  it("loads the list once", async () => {
    vi.mocked(playbooksApi.listPlaybooks).mockResolvedValue({
      items: [{ name: "a", steps: [] }],
      total: 1,
    });

    await useRunsStore.getState().loadPlaybooks();
    await useRunsStore.getState().loadPlaybooks();

    expect(playbooksApi.listPlaybooks).toHaveBeenCalledTimes(1);
    expect(useRunsStore.getState().playbooksStatus).toBe("ready");
  });

  it("can load again after an error", async () => {
    vi.mocked(playbooksApi.listPlaybooks).mockRejectedValueOnce(new Error("offline"));
    vi.mocked(playbooksApi.listPlaybooks).mockResolvedValueOnce({ items: [], total: 0 });

    await useRunsStore.getState().loadPlaybooks();
    expect(useRunsStore.getState().playbooksError).toBe("Offline");

    await useRunsStore.getState().loadPlaybooks();
    expect(useRunsStore.getState().playbooksStatus).toBe("ready");
  });

  it("asks for a playbook's detail once however often it is wanted", async () => {
    vi.mocked(playbooksApi.getPlaybook).mockResolvedValue(playbook);

    await Promise.all([
      useRunsStore.getState().loadPlaybookDetail(playbook.name),
      useRunsStore.getState().loadPlaybookDetail(playbook.name),
    ]);
    await useRunsStore.getState().loadPlaybookDetail(playbook.name);

    expect(playbooksApi.getPlaybook).toHaveBeenCalledTimes(1);
    expect(useRunsStore.getState().playbookDetails[playbook.name]).toBe(playbook);
  });
});

describe("prepareNewRun", () => {
  it("preselects and starts a new form each time", () => {
    useRunsStore.getState().prepareNewRun({ scenario: "s", playbook: "p" });
    const first = useRunsStore.getState();
    expect([first.selectedScenario, first.selectedPlaybook]).toEqual(["s", "p"]);

    useRunsStore.getState().prepareNewRun();
    const second = useRunsStore.getState();
    expect([second.selectedScenario, second.selectedPlaybook]).toEqual([null, null]);
    expect(second.newRunSession).toBe(first.newRunSession + 1);
  });
});
