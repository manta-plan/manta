import type { RunDraft } from "./types";

// Drafts by project, so a reload keeps them. localStorage can throw or be empty (private
// window, blocked site data), so every read and write is guarded and the app works without it.
const DRAFTS_STORAGE_KEY = "manta-run-drafts-v1";

function isDraft(value: unknown): value is RunDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Record<string, unknown>;

  return (
    typeof draft.id === "string" &&
    typeof draft.projectId === "string" &&
    typeof draft.playbook === "string" &&
    typeof draft.createdAt === "string" &&
    typeof draft.config === "object" &&
    draft.config !== null &&
    typeof draft.dataRecord === "object" &&
    draft.dataRecord !== null
  );
}

export function loadDrafts(): RunDraft[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(DRAFTS_STORAGE_KEY) ?? "{}");

    if (typeof stored !== "object" || stored === null) return [];

    // Entries that are not drafts (an older or edited store) are dropped, not trusted.
    return Object.values(stored).flatMap((list) =>
      Array.isArray(list) ? list.filter(isDraft) : [],
    );
  } catch {
    return [];
  }
}

export function saveDrafts(drafts: RunDraft[]): void {
  const byProject: Record<string, RunDraft[]> = {};

  for (const draft of drafts) {
    (byProject[draft.projectId] ??= []).push(draft);
  }

  try {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(byProject));
  } catch {
    // A full or blocked store: the drafts stay in memory for this page.
  }
}
