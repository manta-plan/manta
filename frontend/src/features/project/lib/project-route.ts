export type ProjectTab = "model" | "run" | "inspect" | "report";

// The active tab is derived from the URL rather than stored as separate
// state, since /project/:id, /project/:id/run, and /project/:id/report are
// now real routes — keeping a parallel activeTab field in the store would
// just be another thing that could drift out of sync with the location.
export function getActiveProjectTab(location: string): ProjectTab {
  if (/\/run(?:\/[^/]+)?$/.test(location)) return "run";
  if (/\/inspect(?:\/[^/]+)?$/.test(location)) return "inspect";
  if (/\/report(?:\/[^/]+)?$/.test(location)) return "report";
  return "model";
}

export function projectTabHref(projectId: string, tab: ProjectTab): string {
  return tab === "model" ? `/project/${projectId}` : `/project/${projectId}/${tab}`;
}

export function projectRunHref(projectId: string, runId?: string): string {
  const baseHref = projectTabHref(projectId, "run");
  return runId ? `${baseHref}/${runId}` : baseHref;
}

export function projectInspectHref(projectId: string, inspectionId?: string): string {
  const baseHref = projectTabHref(projectId, "inspect");
  return inspectionId ? `${baseHref}/${inspectionId}` : baseHref;
}

export function projectReportHref(projectId: string, reportId?: string): string {
  const baseHref = projectTabHref(projectId, "report");
  return reportId ? `${baseHref}/${reportId}` : baseHref;
}
