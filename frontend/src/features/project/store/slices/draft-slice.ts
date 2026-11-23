// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import {
  loadProjectDrafts,
  saveProjectDrafts,
  type ChangeDialogSeed,
  type DraftChange,
  type DraftChangeInput,
  type DraftScenario,
  type EntityDialogSeed,
} from "../../lib/draft-scenarios";
import type { ProjectStoreGet, ProjectStoreSet } from "../types";

// Draft scenarios (see lib/draft-scenarios): the project's, which one the Build
// tab shows, and the dialogs that make and change them. They stay in the
// browser (localStorage, per project) until scenarios can be saved to a record.

const newId = (prefix: string) => `${prefix}-${crypto.randomUUID()}`;

export function createDraftSlice(set: ProjectStoreSet, get: ProjectStoreGet) {
  // Every change to the drafts is saved with the project.
  const update = (change: (drafts: DraftScenario[]) => DraftScenario[]) =>
    set((state) => {
      const drafts = change(state.draftScenarios);
      saveProjectDrafts(state.currentProjectId, drafts);
      return { draftScenarios: drafts };
    });
  const touch = (draft: DraftScenario, patch: Partial<DraftScenario>): DraftScenario => ({
    ...draft,
    ...patch,
    updatedAt: new Date().toISOString(),
  });

  return {
    draftScenarios: [] as DraftScenario[],
    loadProjectDrafts: (projectId: string) =>
      set({ draftScenarios: loadProjectDrafts(projectId), shownDraftId: null }),

    createDraft: (input: {
      recordId: string;
      parent: string;
      name: string;
      description: string;
    }): DraftScenario => {
      const now = new Date().toISOString();
      const draft: DraftScenario = {
        id: newId("draft"),
        ...input,
        name: input.name.trim(),
        description: input.description.trim(),
        changes: [],
        createdAt: now,
        updatedAt: now,
      };
      update((drafts) => [...drafts, draft]);
      return draft;
    },
    updateDraft: (id: string, patch: { name?: string; description?: string }) =>
      update((drafts) =>
        drafts.map((draft) =>
          draft.id === id
            ? touch(draft, { ...patch, name: (patch.name ?? draft.name).trim() })
            : draft,
        ),
      ),
    deleteDraft: (id: string) => {
      update((drafts) => drafts.filter((draft) => draft.id !== id));
      if (get().shownDraftId === id) set({ shownDraftId: null });
    },
    /** Adds the change, or replaces the draft's change with its id. */
    saveDraftChange: (draftId: string, change: DraftChangeInput) =>
      update((drafts) =>
        drafts.map((draft) => {
          if (draft.id !== draftId) return draft;
          const saved = { ...change, id: change.id ?? newId("change") } as DraftChange;
          const exists = draft.changes.some((item) => item.id === saved.id);
          return touch(draft, {
            changes: exists
              ? draft.changes.map((item) => (item.id === saved.id ? saved : item))
              : [...draft.changes, saved],
          });
        }),
      ),
    removeDraftChange: (draftId: string, changeId: string) =>
      update((drafts) =>
        drafts.map((draft) =>
          draft.id === draftId
            ? touch(draft, { changes: draft.changes.filter((change) => change.id !== changeId) })
            : draft,
        ),
      ),

    // Showing a draft shows its parent: the server has only that. Showing
    // anything else (showScenario) stops showing the draft.
    shownDraftId: null as string | null,
    showDraft: (id: string) => {
      const draft = get().draftScenarios.find((item) => item.id === id);
      if (!draft) return;
      get().showScenario(draft.parent);
      set({ shownDraftId: id });
    },

    scenarioDialog: null as { mode: "new" } | { mode: "edit"; draftId: string } | null,
    openScenarioDialog: (dialog: { mode: "new" } | { mode: "edit"; draftId: string }) =>
      set({ scenarioDialog: dialog }),
    closeScenarioDialog: () => set({ scenarioDialog: null }),

    changeDialog: null as ChangeDialogSeed | null,
    openChangeDialog: (seed: ChangeDialogSeed) => set({ changeDialog: seed }),
    closeChangeDialog: () => set({ changeDialog: null }),

    entityDialog: null as EntityDialogSeed | null,
    openEntityDialog: (seed: EntityDialogSeed) => set({ entityDialog: seed }),
    closeEntityDialog: () => set({ entityDialog: null }),
  };
}
