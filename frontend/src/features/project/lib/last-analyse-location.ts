// Where the user last was on Analyse, so the tab reopens it instead of the
// overview. Kept per project and for the session only.
const lastByProject = new Map<string, string>();

export function rememberAnalyseLocation(projectId: string, href: string) {
  lastByProject.set(projectId, href);
}

export function lastAnalyseLocation(projectId: string): string | undefined {
  return lastByProject.get(projectId);
}
