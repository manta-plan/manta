import type { Report } from "../data/reports";
import { presetTheme } from "../data/report-themes";
import { mergeWithStored } from "./stored-lists";

// v2 is the paper report builder; the earlier stat/chart reports (v1) can't be converted and are dropped.
export const PROJECT_REPORTS_STORAGE_KEY = "manta-project-reports-v2";
const LEGACY_REPORTS_STORAGE_KEY = "manta-project-reports-v1";

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
  if (typeof localStorage !== "undefined") localStorage.removeItem(LEGACY_REPORTS_STORAGE_KEY);
  // Reports saved before themes existed get the default one, and themes saved before decoration get their preset's.
  return (storedReports()[projectId] ?? []).map((report) => {
    const theme = report.theme ?? presetTheme("paper");
    return {
      ...report,
      theme: theme.decoration ? theme : { ...theme, decoration: presetTheme(theme.id).decoration },
    };
  });
}

export function saveProjectReports(projectId: string | null, reports: Report[]) {
  if (!projectId || typeof localStorage === "undefined") return;
  const stored = storedReports();
  // Another tab may have added reports since this one loaded.
  stored[projectId] = mergeWithStored(reports, stored[projectId]);
  try {
    localStorage.setItem(PROJECT_REPORTS_STORAGE_KEY, JSON.stringify(stored));
  } catch (error) {
    // Out of space (images are the usual cause): the report stays open but this change isn't kept.
    console.warn("Could not save the reports", error);
  }
}

export function removeProjectReports(projectId: string) {
  if (typeof localStorage === "undefined") return;
  const stored = storedReports();
  if (!(projectId in stored)) return;
  delete stored[projectId];
  localStorage.setItem(PROJECT_REPORTS_STORAGE_KEY, JSON.stringify(stored));
}
