// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { Revision } from "../project/lib/record-server/types";

/** The record's scenarios, parents first, so a scenario follows the one it starts from. */
export function listRecordScenarios(revisions: Revision[]): Revision[] {
  const byName = new Map(revisions.map((revision) => [revision.name, revision]));
  const depth = (revision: Revision, seen: Set<string>): number => {
    const parent = revision.parent === null ? undefined : byName.get(revision.parent);

    // `seen` stops a cycle in malformed data.
    if (parent === undefined || seen.has(parent.name)) {
      return 0;
    }

    return 1 + depth(parent, seen.add(revision.name));
  };

  return revisions
    .filter((revision) => revision.kind === "scenario")
    .sort((a, b) => depth(a, new Set()) - depth(b, new Set()));
}
