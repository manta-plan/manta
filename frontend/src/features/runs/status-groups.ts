// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { normalizeRunStatus } from "./status";
import type { GetRunSummaryResponse, RunStatus } from "./types";

// The four numbers of the Run Workspace. CANCELLING, CANCELLED and PAUSED count only in the total.
const succeededStatuses = ["COMPLETED"];
const inProgressStatuses = ["SCHEDULED", "PENDING", "RUNNING"];
const failedStatuses = ["FAILED", "TIMED_OUT", "CRASHED"];

export type RunStatusCounts = {
  total: number;
  succeeded: number;
  inProgress: number;
  failed: number;
  /** Percent of finished runs (succeeded + failed) that succeeded; null while none has finished. */
  successRate: number | null;
};

function countOf(statuses: Record<string, number>, names: string[]): number {
  return Object.entries(statuses).reduce(
    (sum, [status, count]) => (names.includes(normalizeRunStatus(status)) ? sum + count : sum),
    0,
  );
}

export function summarizeRunStatuses(summary: GetRunSummaryResponse): RunStatusCounts {
  const succeeded = countOf(summary.statuses, succeededStatuses);
  const failed = countOf(summary.statuses, failedStatuses);
  const finished = succeeded + failed;

  return {
    total: summary.total,
    succeeded,
    inProgress: countOf(summary.statuses, inProgressStatuses),
    failed,
    successRate: finished > 0 ? Math.round((succeeded / finished) * 100) : null,
  };
}

/** The pseudo status of a draft in the Run Filters. The backend knows nothing of it. */
export const draftStatus = "DRAFT";

/**
 * Splits the selected filters. Only the Prefect states go to the backend; drafts are local, and
 * are listed when nothing is selected or Draft is.
 */
export function splitStatusFilter(selected: RunStatus[]): {
  serverStatuses: RunStatus[];
  showsDrafts: boolean;
  /** Only Draft is selected: no run of the backend can match, so it is not asked. */
  isDraftOnly: boolean;
} {
  const serverStatuses = selected.filter((status) => status !== draftStatus);

  return {
    serverStatuses,
    showsDrafts: selected.length === 0 || selected.includes(draftStatus),
    isDraftOnly: selected.length > 0 && serverStatuses.length === 0,
  };
}
