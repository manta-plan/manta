import { useSyncExternalStore } from "react";
import type { InspectResult, ResultCatalogue } from "./result-source";

// The result the Inspect tab shows, and the one it compares with: one
// choice for the whole tab, made in the toolbar, so every inspection is a
// review page pointed at the same result. It's kept as `?result=&compare=`
// while an inspection is open, so a link opens the same view.

const RESULT_PARAM = "result";
const COMPARE_PARAM = "compare";

export interface ResultSelection {
  /** Empty means the newest result. */
  resultId: string;
  /** Empty means no comparison. */
  comparisonId: string;
}

function fromUrl(): ResultSelection {
  const params = new URLSearchParams(window.location.search);
  return {
    resultId: params.get(RESULT_PARAM) ?? "",
    comparisonId: params.get(COMPARE_PARAM) ?? "",
  };
}

let selection: ResultSelection = fromUrl();
const listeners = new Set<() => void>();

function setSelection(next: ResultSelection) {
  selection = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useResultSelection(): ResultSelection {
  return useSyncExternalStore(subscribe, () => selection);
}

/** The selection as runs of the catalogue: unknown ids fall back to the newest result and no comparison. */
export function resolveResultSelection(
  catalogue: ResultCatalogue,
  current: ResultSelection,
): { selectedRun: InspectResult; comparisonRun: InspectResult | null } {
  const { results } = catalogue;
  const selectedRun = results.find((run) => run.id === current.resultId) ?? results[0];
  const comparisonRun =
    results.find((run) => run.id === current.comparisonId && run.id !== selectedRun.id) ?? null;
  return { selectedRun, comparisonRun };
}

/** A result can't be compared with itself, so picking the compared one drops the comparison. */
export function selectResult(resultId: string) {
  setSelection({
    resultId,
    comparisonId: selection.comparisonId === resultId ? "" : selection.comparisonId,
  });
}

export function selectComparison(comparisonId: string) {
  setSelection({ ...selection, comparisonId });
}

/** Puts the selection in the address bar, or takes it out (`clear`) when no inspection is open. */
export function writeResultSelectionToUrl(clear = false) {
  const url = new URL(window.location.href);
  const set = (name: string, value: string) =>
    value && !clear ? url.searchParams.set(name, value) : url.searchParams.delete(name);
  set(RESULT_PARAM, selection.resultId);
  set(COMPARE_PARAM, selection.comparisonId);
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url);
}
