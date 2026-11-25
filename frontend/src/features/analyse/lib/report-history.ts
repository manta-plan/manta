import type { PageSetup, Report, ReportPage } from "../data/reports";
import type { ReportTheme } from "../data/report-themes";

// Undo and redo for the report editor. A step is a snapshot of what an edit
// can change: the report's name, paper, theme and pages. Edits share their
// unchanged parts, so a snapshot costs little even with images in the report.
// History lives in memory, per report, and starts afresh when the project loads.

export type ReportSnapshot = Pick<Report, "name" | "page" | "theme" | "pages">;

export interface HistoryStep {
  /** What the edit did, for the undo button's tooltip. */
  label: string;
  snapshot: ReportSnapshot;
}

export interface ReportHistory {
  past: HistoryStep[];
  future: HistoryStep[];
  /** The last edit's merge key and time, so a burst of the same edit makes one step. */
  lastKey: string | null;
  lastAt: number;
}

export type ReportHistories = Record<string, ReportHistory>;

export interface EditOptions {
  /** What the edit did, for the undo button's tooltip. */
  label?: string;
  /** Edits with the same key in quick succession make one undo step. */
  mergeKey?: string;
}

const MAX_STEPS = 100;
/** Edits with the same key closer together than this are one step. */
const MERGE_WINDOW_MS = 700;

export const EMPTY_HISTORY: ReportHistory = { past: [], future: [], lastKey: null, lastAt: 0 };

export function snapshotOf(report: Report): ReportSnapshot {
  return {
    name: report.name,
    page: report.page as PageSetup,
    theme: report.theme as ReportTheme,
    pages: report.pages as ReportPage[],
  };
}

/** The histories with an edit about to be made to `report` recorded: its current state becomes an undo step. */
export function recordEdit(
  histories: ReportHistories,
  report: Report,
  label: string,
  mergeKey: string | null,
  now: number,
): ReportHistories {
  const history = histories[report.id] ?? EMPTY_HISTORY;
  const isMerged =
    mergeKey !== null &&
    history.lastKey === mergeKey &&
    now - history.lastAt < MERGE_WINDOW_MS &&
    history.past.length > 0;
  if (isMerged) return { ...histories, [report.id]: { ...history, lastAt: now, future: [] } };
  const past = [...history.past, { label, snapshot: snapshotOf(report) }].slice(-MAX_STEPS);
  return { ...histories, [report.id]: { past, future: [], lastKey: mergeKey, lastAt: now } };
}

/** One step back: the snapshot to restore, and the histories with the report's current state kept for redo. */
export function stepBack(
  histories: ReportHistories,
  report: Report,
): { snapshot: ReportSnapshot; histories: ReportHistories } | null {
  const history = histories[report.id];
  const step = history?.past[history.past.length - 1];
  if (!history || !step) return null;
  const next: ReportHistory = {
    past: history.past.slice(0, -1),
    future: [...history.future, { label: step.label, snapshot: snapshotOf(report) }],
    lastKey: null,
    lastAt: 0,
  };
  return { snapshot: step.snapshot, histories: { ...histories, [report.id]: next } };
}

/** One step forward again, after an undo. */
export function stepForward(
  histories: ReportHistories,
  report: Report,
): { snapshot: ReportSnapshot; histories: ReportHistories } | null {
  const history = histories[report.id];
  const step = history?.future[history.future.length - 1];
  if (!history || !step) return null;
  const next: ReportHistory = {
    past: [...history.past, { label: step.label, snapshot: snapshotOf(report) }],
    future: history.future.slice(0, -1),
    lastKey: null,
    lastAt: 0,
  };
  return { snapshot: step.snapshot, histories: { ...histories, [report.id]: next } };
}

export function forgetHistory(histories: ReportHistories, reportId: string): ReportHistories {
  const { [reportId]: _removed, ...rest } = histories;
  return rest;
}
