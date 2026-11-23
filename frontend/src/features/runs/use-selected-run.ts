// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { draftIdPrefix, useRunsStore } from "./store/runs-store";
import type { GetRunResponse, RunDraft, RunListItem } from "./types";

export type SelectedRun =
  | { kind: "draft"; draft: RunDraft }
  | {
      kind: "run";
      run: RunListItem;
      /** The run's own record; null until it has loaded. */
      detail: GetRunResponse | null;
    }
  /** On neither the page loaded nor the drafts; the backend is being asked. */
  | { kind: "loading" }
  /** The backend has no such run in this project. */
  | { kind: "missing" }
  | { kind: "error"; message: string };

/**
 * The run the URL names: a draft, a run of the loaded page, or one looked up by its id.
 * Derived from the runs store, so it never goes out of step with the list. It only reads;
 * the run workspace starts the lookup.
 */
export function useSelectedRun(runId: string | undefined): SelectedRun | null {
  const draft = useRunsStore((s) => s.drafts.find((item) => item.id === runId));
  const listed = useRunsStore((s) => s.runs.find((item) => item.id === runId));
  const lookedUp = useRunsStore((s) => s.lookedUpRun);
  const detail = useRunsStore((s) =>
    runId === undefined ? undefined : s.expandedRuns[runId]?.detail,
  );

  if (runId === undefined) {
    return null;
  }

  if (draft !== undefined) {
    return { kind: "draft", draft };
  }

  // A draft that is gone (deleted, or lost on reload) is not a run to look up.
  if (runId.startsWith(draftIdPrefix) && draft === undefined) {
    return { kind: "missing" };
  }

  const run = listed ?? (lookedUp?.id === runId ? lookedUp.run : null);

  if (run !== null && run !== undefined) {
    return { kind: "run", run, detail: detail ?? null };
  }

  if (lookedUp?.id === runId) {
    return lookedUp.error === null
      ? { kind: "missing" }
      : { kind: "error", message: lookedUp.error };
  }

  return { kind: "loading" };
}
