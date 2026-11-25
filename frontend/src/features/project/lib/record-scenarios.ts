import type { RecordInfo, Revision } from "./record-server/types";

// Which of a record's scenarios the project page can show, and which one it
// shows: its scenarios (Build) and their run results (Inspect), each read from
// its own catalog on the server.

const URL_PARAM = "scenario";

export function isRunResult(revision: Revision | undefined): boolean {
  return revision?.kind === "result";
}

export function runResultsOf(info: RecordInfo, scenario: string): Revision[] {
  return info.revisions.filter(
    (revision) => isRunResult(revision) && revision.parent === scenario && revision.catalog,
  );
}

// Every revision the page can show: each scenario, then its run results.
export function showableRevisions(info: RecordInfo): Revision[] {
  return selectableScenarios(info).flatMap((scenario) => [
    scenario,
    ...runResultsOf(info, scenario.name),
  ]);
}

// A run result's label without its scenario's ("Base case, myopic" under
// "Base case" reads "Myopic").
export function shortLabel(info: RecordInfo, revision: Revision): string {
  const parent = info.revisions.find((item) => item.name === revision.parent);
  if (!isRunResult(revision) || !parent) return revision.label;
  const prefix = `${parent.label}, `;
  if (!revision.label.startsWith(prefix) || revision.label.length === prefix.length)
    return revision.label;
  const rest = revision.label.slice(prefix.length);
  return rest[0].toUpperCase() + rest.slice(1);
}

export function selectableScenarios(info: RecordInfo): Revision[] {
  return info.revisions.filter((revision) => revision.kind === "scenario" && revision.catalog);
}

export function defaultScenario(info: RecordInfo): string | null {
  return info.defaultScenario;
}

export function scenarioCatalog(info: RecordInfo, name: string | null): string | null {
  return info.revisions.find((item) => item.name === name)?.catalog ?? null;
}

// The label of the revision a scenario starts from: what its changes are against.
export function parentLabel(info: RecordInfo, name: string | null): string {
  const parent = info.revisions.find((revision) => revision.name === name)?.parent;
  return info.revisions.find((revision) => revision.name === parent)?.label ?? "its parent";
}

// `?scenario=` if it names a revision that can be shown, else the default.
export function initialScenario(info: RecordInfo): string | null {
  const requested = new URLSearchParams(window.location.search).get(URL_PARAM);
  return showableRevisions(info).some((revision) => revision.name === requested)
    ? requested
    : defaultScenario(info);
}

// Keeps `?scenario=` in the address bar, so a reload or a shared link shows
// the same scenario; the default one leaves the URL clean.
export function writeScenarioToUrl(info: RecordInfo, name: string | null): void {
  const url = new URL(window.location.href);
  if (name && name !== defaultScenario(info)) url.searchParams.set(URL_PARAM, name);
  else url.searchParams.delete(URL_PARAM);
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url);
}
