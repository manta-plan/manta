import { INITIAL_RUNS, type Run } from "../data/runs";

const PROJECT_RUNS_STORAGE_KEY = "manta-project-runs-v1";

function defaultRuns(): Run[] {
  return structuredClone(INITIAL_RUNS);
}

function storedRuns(): Record<string, Run[]> {
  if (typeof localStorage === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(PROJECT_RUNS_STORAGE_KEY) ?? "{}") as Record<
      string,
      Run[]
    >;
  } catch {
    return {};
  }
}

// A run still "running" at load lost its timer with the old page, so it can
// never finish; show it as failed instead of spinning forever.
export function loadProjectRuns(projectId: string): Run[] {
  const runs = storedRuns()[projectId];
  if (!runs) return defaultRuns();
  return runs.map((run) =>
    run.status === "running" ? { ...run, status: "failed", duration: null } : run,
  );
}

export function saveProjectRuns(projectId: string | null, runs: Run[]) {
  if (!projectId || typeof localStorage === "undefined") return;
  const stored = storedRuns();
  stored[projectId] = runs;
  localStorage.setItem(PROJECT_RUNS_STORAGE_KEY, JSON.stringify(stored));
}

export function removeProjectRuns(projectId: string) {
  if (typeof localStorage === "undefined") return;
  const stored = storedRuns();
  if (!(projectId in stored)) return;
  delete stored[projectId];
  localStorage.setItem(PROJECT_RUNS_STORAGE_KEY, JSON.stringify(stored));
}
