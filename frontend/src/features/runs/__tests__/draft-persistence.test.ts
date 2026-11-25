// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RunDraft } from "../types";

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
import { loadDrafts, saveDrafts } from "../draft-storage";
import { useRunsStore } from "../store/runs-store";

const initialState = useRunsStore.getState();

// The tests run in node, which has no window: a small in-memory localStorage stands in.
const memory = new Map<string, string>();
const storage = {
  getItem: (key: string) => memory.get(key) ?? null,
  setItem: (key: string, value: string) => void memory.set(key, value),
  clear: () => memory.clear(),
};

function draft(id: string, projectId = "project-1", playbookName = "pb"): RunDraft {
  return {
    id,
    projectId,
    playbook: playbookName,
    dataRecord: { name: "rec", revision_uuid: "rev" },
    scenarioId: null,
    scenarioLabel: null,
    config: {},
    createdAt: "2026-11-01T10:00:00Z",
  } as RunDraft;
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("window", { localStorage: storage });
  storage.clear();
  useRunsStore.setState({ ...initialState, drafts: [] }, true);
});

describe("draft storage", () => {
  it("keeps drafts of every project across a save and a load", () => {
    saveDrafts([draft("a"), draft("b", "project-2")]);

    expect(
      loadDrafts()
        .map((item) => item.id)
        .sort(),
    ).toEqual(["a", "b"]);
  });

  it("drops entries that are not drafts and survives bad JSON", () => {
    storage.setItem(
      "manta-run-drafts-v1",
      JSON.stringify({ "project-1": [draft("a"), { id: 1 }, "x"] }),
    );
    expect(loadDrafts().map((item) => item.id)).toEqual(["a"]);

    storage.setItem("manta-run-drafts-v1", "{not json");
    expect(loadDrafts()).toEqual([]);
  });

  it("does not throw when the storage refuses a write", () => {
    vi.stubGlobal("window", {
      localStorage: {
        ...storage,
        setItem: () => {
          throw new Error("quota");
        },
      },
    });

    expect(() => saveDrafts([draft("a")])).not.toThrow();
  });
});

describe("saving from the store", () => {
  it("saves on create and delete", () => {
    const created = useRunsStore.getState().createDraft({
      projectId: "project-1",
      playbook: "pb",
      dataRecord: { name: "rec", revision_uuid: "rev" },
      scenarioId: null,
      scenarioLabel: null,
      config: {},
    });

    expect(loadDrafts().map((item) => item.id)).toEqual([created.id]);

    useRunsStore.getState().deleteDraft(created.id);

    expect(loadDrafts()).toEqual([]);
  });

  it("drops a saved draft whose playbook is gone once the playbooks load", async () => {
    useRunsStore.setState({ drafts: [draft("keep", "project-1", "here"), draft("gone")] });
    vi.mocked(playbooksApi.listPlaybooks).mockResolvedValue({
      items: [{ name: "here" }],
    } as Awaited<ReturnType<typeof playbooksApi.listPlaybooks>>);

    await useRunsStore.getState().loadPlaybooks();

    expect(useRunsStore.getState().drafts.map((item) => item.id)).toEqual(["keep"]);
    expect(loadDrafts().map((item) => item.id)).toEqual(["keep"]);
  });
});

describe("init for another project", () => {
  it("starts on the first page with no filter, search or open run", async () => {
    vi.mocked(runsApi.listRuns).mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
      summary: { total: 0, statuses: {} },
    });
    useRunsStore.setState({
      projectId: "project-a",
      runsOffset: 20,
      selectedStatuses: ["FAILED"],
      searchRunId: "x",
      activeSearchRunId: "x",
      expandedRunId: "r1",
      expandedRuns: { r1: { isLoading: false, error: null, detail: null, logs: null } },
    });

    await useRunsStore.getState().init("project-b", "ada");

    const state = useRunsStore.getState();
    expect(state.projectId).toBe("project-b");
    expect(state.runsOffset).toBe(0);
    expect(state.selectedStatuses).toEqual([]);
    expect(state.activeSearchRunId).toBe("");
    expect(state.expandedRuns).toEqual({});
    expect(vi.mocked(runsApi.listRuns).mock.calls[0][1]).toMatchObject({ offset: 0 });
  });

  it("keeps the filter when the same project is initialised again", async () => {
    vi.mocked(runsApi.listRuns).mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
      summary: { total: 0, statuses: {} },
    });
    useRunsStore.setState({ projectId: "project-a", selectedStatuses: ["FAILED"] });

    await useRunsStore.getState().init("project-a", "ada");

    expect(useRunsStore.getState().selectedStatuses).toEqual(["FAILED"]);
  });
});
