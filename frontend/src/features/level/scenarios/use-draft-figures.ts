// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import {
  applyChanges,
  targetMatches,
  type DraftAttributeChange,
  type DraftScenario,
} from "../../project/lib/draft-scenarios";
import { useShownData } from "../../project/lib/record-data";
import { useProjectStore } from "../../project/store/project-store";
import { usePeriods } from "../periods";
import { formatValue } from "./change-wording";
import { loadDraftFigures, valueKey, type DraftFigures } from "./change-sql";

// What the Scenarios panel shows beside a draft's changes: how many entities
// a filter change matches, and a single-entity change's value before and
// after. Read in the shown catalog, so only while the draft's parent is the
// scenario shown (else null).

export function useDraftFigures(draft: DraftScenario): DraftFigures | null {
  const scenario = useProjectStore((s) => s.record?.scenario ?? null);
  const { period } = usePeriods();
  const changes = draft.changes.filter((change) => change.kind === "attribute");
  const args =
    draft.parent === scenario && period && changes.length > 0
      ? [draft.id, JSON.stringify(changes), period]
      : null;
  const figures = useShownData("draft-figures", args, () => loadDraftFigures(changes, period!));
  return figures.status === "ready" ? figures.data : null;
}

/** "1,200 → 1,560", "series × 1.3", or null while the value isn't read. */
export function beforeAfter(
  draft: DraftScenario,
  change: DraftAttributeChange,
  figures: DraftFigures | null,
  opText: string,
): { before: string; after: string } | null {
  if (change.target.kind !== "entity" || !figures) return null;
  const stored = figures.values[valueKey(change.target.entity, change.attribute)];
  if (stored && stored.seriesRows > 0)
    return change.op === "set"
      ? { before: "series", after: formatValue(change.value) }
      : { before: "series", after: `series ${opText}` };
  // The value as the draft's earlier changes leave it.
  const { entity, ctype, carrier, location } = change.target;
  const subject = { entity, ctype, carrier, locations: location ? [location] : [] };
  const index = draft.changes.indexOf(change);
  const earlier = draft.changes
    .slice(0, index)
    .filter(
      (item): item is DraftAttributeChange =>
        item.kind === "attribute" &&
        item.attribute === change.attribute &&
        targetMatches(item.target, subject),
    );
  const before = applyChanges(stored?.value ?? null, earlier);
  const after = applyChanges(before, [change]);
  // No stored value: the manifest's default, which isn't read here.
  return {
    before: before === null ? "default" : formatValue(before),
    after: after === null ? `default ${opText}` : formatValue(after),
  };
}
