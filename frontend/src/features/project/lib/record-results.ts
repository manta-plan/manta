// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { isRunResult } from "./record-scenarios";
import type { RecordInfo } from "./record-server/types";

/**
 * One result the Inspect page shows: a solved revision of the project's
 * record ("Base case, myopic"), not a Manta run.
 */
export interface InspectResult {
  /** The revision's name in the record, e.g. `patch/myopic`; what `?scenario=` holds on Inspect. */
  id: string;
  label: string;
  /** The scenario it was solved from. */
  scenario: string | null;
  scenarioLabel: string;
  /** The server catalog holding its values. */
  catalog: string;
}

// The results the Inspect page lists: the record's solved revisions, in the
// record's order, each with the scenario it was solved from.
export function recordResults(info: RecordInfo): InspectResult[] {
  return info.revisions.flatMap((revision) => {
    if (!isRunResult(revision) || !revision.catalog) return [];
    const scenario = info.revisions.find((item) => item.name === revision.parent) ?? null;
    return [
      {
        id: revision.name,
        label: revision.label,
        scenario: scenario?.name ?? null,
        scenarioLabel: scenario?.label ?? "",
        catalog: revision.catalog,
      },
    ];
  });
}
