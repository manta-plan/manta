import type { Report } from "../data/reports";

const PROJECT_REPORTS_STORAGE_KEY = "manta-project-reports-v1";

function storedReports(): Record<string, Report[]> {
  if (typeof localStorage === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(PROJECT_REPORTS_STORAGE_KEY) ?? "{}") as Record<
      string,
      Report[]
    >;
  } catch {
    return {};
  }
}

export function loadProjectReports(projectId: string): Report[] {
  return storedReports()[projectId] ?? [];
}

export function saveProjectReports(projectId: string | null, reports: Report[]) {
  if (!projectId || typeof localStorage === "undefined") return;
  const stored = storedReports();
  stored[projectId] = reports;
  localStorage.setItem(PROJECT_REPORTS_STORAGE_KEY, JSON.stringify(stored));
}

export function removeProjectReports(projectId: string) {
  if (typeof localStorage === "undefined") return;
  const stored = storedReports();
  if (!(projectId in stored)) return;
  delete stored[projectId];
  localStorage.setItem(PROJECT_REPORTS_STORAGE_KEY, JSON.stringify(stored));
}
