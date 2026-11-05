import type { RecordInfo, Revision } from "./record-server/types";

// Which of a record's scenarios the project page can show, and which one it
// shows. Each is read from its own catalog on the server. Run results aren't
// shown here (the Inspect page, later).

const URL_PARAM = "scenario";

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

// `?scenario=` if it names a scenario that can be shown, else the default.
export function initialScenario(info: RecordInfo): string | null {
  const requested = new URLSearchParams(window.location.search).get(URL_PARAM);
  return selectableScenarios(info).some((revision) => revision.name === requested)
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
