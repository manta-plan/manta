// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useMemo } from "react";
import { useLocation } from "wouter";
import { useProjectStore } from "../store/project-store";
import type { DraftScenario } from "./draft-scenarios";
import { getActiveProjectTab } from "./project-route";

/** The draft the Build tab shows: only there, and while the record shows its parent. */
export function useShownDraft(): DraftScenario | null {
  const [location] = useLocation();
  const onBuild = getActiveProjectTab(location) === "build";
  const shownDraftId = useProjectStore((s) => s.shownDraftId);
  const drafts = useProjectStore((s) => s.draftScenarios);
  const record = useProjectStore((s) => s.record);
  return useMemo(() => {
    if (!onBuild || !shownDraftId || !record) return null;
    const draft = drafts.find((item) => item.id === shownDraftId);
    return draft && draft.recordId === record.info.id && draft.parent === record.scenario
      ? draft
      : null;
  }, [drafts, onBuild, record, shownDraftId]);
}

/** The record's drafts (this project's), for the shown record. */
export function useRecordDrafts(): DraftScenario[] {
  const record = useProjectStore((s) => s.record);
  const drafts = useProjectStore((s) => s.draftScenarios);
  return useMemo(
    () => (record ? drafts.filter((draft) => draft.recordId === record.info.id) : []),
    [drafts, record],
  );
}
