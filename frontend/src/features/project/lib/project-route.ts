// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

export type ProjectTab = "build" | "run" | "inspect" | "analyse";

// The active tab is derived from the URL rather than stored as separate
// state: /project/:id/build, /run, /inspect and /analyse are real routes (the
// last segment may be a page id: a level page, a run), so keeping a parallel
// activeTab field in the store would just be another thing that could drift
// out of sync with the location. /project/:id alone is Build.
export function getActiveProjectTab(location: string): ProjectTab {
  const path = location.split(/[?#]/)[0];
  if (/\/run(?:\/[^/]+)?$/.test(path)) return "run";
  if (/\/inspect(?:\/[^/]+)?$/.test(path)) return "inspect";
  if (/\/analyse(?:\/[^/]+)?$/.test(path)) return "analyse";
  return "build";
}

export function projectTabHref(projectId: string, tab: ProjectTab): string {
  return `/project/${projectId}/${tab}`;
}

/** A level page (or comparison) of the record on Build or Inspect; no page id opens All entities. */
export function projectRecordPageHref(
  projectId: string,
  tab: "build" | "inspect",
  pageId?: string | null,
): string {
  const base = projectTabHref(projectId, tab);
  return pageId ? `${base}/${pageId}` : base;
}

export function projectRunHref(projectId: string, runId?: string): string {
  const baseHref = projectTabHref(projectId, "run");
  return runId ? `${baseHref}/${runId}` : baseHref;
}

export function projectInspectHref(projectId: string, pageId?: string): string {
  return projectRecordPageHref(projectId, "inspect", pageId);
}

export function projectAnalyseHref(projectId: string, reportId?: string): string {
  const baseHref = projectTabHref(projectId, "analyse");
  return reportId ? `${baseHref}/${reportId}` : baseHref;
}
