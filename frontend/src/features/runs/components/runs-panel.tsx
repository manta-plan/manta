// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import type { IconType } from "react-icons";
import {
  LuChevronLeft,
  LuChevronRight,
  LuCircleCheck,
  LuCircleDashed,
  LuCircleX,
  LuClock3,
  LuFilePen,
  LuLoaderCircle,
  LuTrash2,
} from "react-icons/lu";
import { Link, useLocation, useParams } from "wouter";
import { ConfirmDialog } from "../../../components/confirm-dialog";
import { projectRunHref } from "../../project/lib/project-route";
import { getRunsPanelEmptyMessage } from "../run-draft";
import { formatRunStatus, normalizeRunStatus } from "../status";
import { splitStatusFilter } from "../status-groups";
import { useRunsStore } from "../store/runs-store";
import type { RunListItem } from "../types";
import { formatRunDuration, formatRunStartedAt } from "../utils";

const statusIcons: Record<string, { icon: IconType; color: string; spins?: boolean }> = {
  COMPLETED: { icon: LuCircleCheck, color: "text-ok-500" },
  FAILED: { icon: LuCircleX, color: "text-danger-500" },
  CRASHED: { icon: LuCircleX, color: "text-danger-500" },
  RUNNING: { icon: LuLoaderCircle, color: "text-accent-400", spins: true },
  SCHEDULED: { icon: LuClock3, color: "text-surface-400" },
  PENDING: { icon: LuClock3, color: "text-surface-400" },
};
const otherStatusIcon = { icon: LuCircleDashed, color: "text-surface-400" };

function subLine(run: RunListItem): string {
  const parts = [formatRunStartedAt(run.startedAt)];

  if (run.durationSeconds !== null) {
    parts.push(formatRunDuration(run.durationSeconds));
  }

  return parts.join(" · ");
}

const rowClassName = (isSelected: boolean) =>
  `flex cursor-pointer items-center gap-2 px-3 py-1.5 text-[12px] outline-none focus-visible:bg-surface-700/60 ${
    isSelected ? "bg-accent-600/25" : "hover:bg-surface-700/60"
  }`;

// Drafts first, then the runs of the backend page; the same list the table shows.
export function RunsPanel() {
  const { projectId, detailId } = useParams<{ projectId: string; detailId?: string }>();
  const [, navigate] = useLocation();
  const runs = useRunsStore((s) => s.runs);
  const runsTotal = useRunsStore((s) => s.runsTotal);
  const runsOffset = useRunsStore((s) => s.runsOffset);
  const runsError = useRunsStore((s) => s.runsError);
  const isRefreshingRuns = useRunsStore((s) => s.isRefreshingRuns);
  const selectedStatuses = useRunsStore((s) => s.selectedStatuses);
  const activeSearchRunId = useRunsStore((s) => s.activeSearchRunId);
  const allDrafts = useRunsStore((s) => s.drafts);
  const deleteDraft = useRunsStore((s) => s.deleteDraft);
  const goToPreviousPage = useRunsStore((s) => s.goToPreviousPage);
  const goToNextPage = useRunsStore((s) => s.goToNextPage);
  const [draftToDelete, setDraftToDelete] = useState<{ id: string; name: string } | null>(null);

  const isSearching = activeSearchRunId.length > 0;
  const isFiltered = selectedStatuses.length > 0 || isSearching;
  // A search names a run of the backend, so drafts are not part of it.
  const drafts =
    isSearching || !splitStatusFilter(selectedStatuses).showsDrafts
      ? []
      : allDrafts.filter((draft) => draft.projectId === projectId);
  const emptyMessage = getRunsPanelEmptyMessage({
    hasRows: drafts.length > 0 || runs.length > 0,
    isFiltered,
  });
  const pageStart = runsTotal > 0 ? runsOffset + 1 : 0;
  const pageEnd = Math.min(runsOffset + runs.length, runsTotal);

  function confirmDeleteDraft() {
    if (draftToDelete === null) {
      return;
    }

    // Leave the deleted draft's page, so the workspace does not point at a missing run.
    if (detailId === draftToDelete.id) {
      navigate(projectRunHref(projectId));
    }

    deleteDraft(draftToDelete.id);
    setDraftToDelete(null);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {runsError ? (
          <div
            className="mx-3 my-2 rounded border border-red-500/40 bg-red-500/10 px-2 py-1.5 text-[12px] text-red-300"
            role="alert"
          >
            {runsError}
          </div>
        ) : null}

        {drafts.map((draft) => {
          const isSelected = detailId === draft.id;

          return (
            <div className="group relative" key={draft.id}>
              <span className="bg-surface-600 text-surface-200 pointer-events-none absolute top-0 left-0 z-10 rounded-br pr-1 pl-0.5 text-[6px] leading-[9px] font-semibold tracking-wide uppercase">
                Draft
              </span>
              <Link
                className={`${rowClassName(isSelected)} group-focus-within:pr-9 group-hover:pr-9`}
                href={projectRunHref(projectId, isSelected ? undefined : draft.id)}
              >
                <LuFilePen className="text-surface-400 shrink-0" size={14} aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="text-surface-50 truncate font-medium">{draft.playbook}</div>
                  <div className="text-surface-400 truncate text-[11px]">
                    {draft.scenarioLabel ? `${draft.scenarioLabel} · ` : ""}
                    Not saved: lost on reload
                  </div>
                </div>
              </Link>
              <div className="absolute top-1/2 right-2 flex -translate-y-1/2 items-center">
                <button
                  aria-label={`Delete draft ${draft.playbook}`}
                  className="text-surface-400 hover:bg-surface-600 hover:text-danger-400 flex h-6 w-6 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100"
                  onClick={() => setDraftToDelete({ id: draft.id, name: draft.playbook })}
                  title="Delete run"
                  type="button"
                >
                  <LuTrash2 size={13} aria-hidden="true" />
                </button>
              </div>
            </div>
          );
        })}

        {runs.map((run) => {
          const meta = statusIcons[normalizeRunStatus(run.status)] ?? otherStatusIcon;
          const Icon = meta.icon;
          const isSelected = detailId === run.id;

          return (
            <Link
              className={rowClassName(isSelected)}
              href={projectRunHref(projectId, isSelected ? undefined : run.id)}
              key={run.id}
            >
              <Icon
                aria-hidden="true"
                className={`shrink-0 ${meta.color} ${meta.spins ? "animate-spin" : ""}`}
                size={14}
              />
              <div className="min-w-0 flex-1">
                <div className="text-surface-50 truncate font-medium">{run.name}</div>
                <div className="text-surface-400 truncate text-[11px]">
                  <span className="sr-only">{formatRunStatus(run.status)}. </span>
                  {subLine(run)}
                </div>
              </div>
            </Link>
          );
        })}

        {emptyMessage === null ? null : (
          <div className="text-surface-400 px-3 py-5 text-center text-[12px]">
            {isRefreshingRuns ? "Loading runs..." : emptyMessage}
          </div>
        )}
      </div>

      {runsTotal > 0 && !isSearching ? (
        <div className="border-surface-600 text-surface-400 flex shrink-0 items-center justify-between gap-2 border-t px-3 py-1.5 text-[11px]">
          <span>
            Showing {pageStart}–{pageEnd} of {runsTotal}
          </span>
          <span className="flex items-center gap-1">
            <button
              aria-label="Previous page of runs"
              className="hover:bg-surface-700 hover:text-surface-100 flex h-5 w-5 items-center justify-center rounded outline-none disabled:pointer-events-none disabled:opacity-40"
              disabled={runsOffset === 0 || isRefreshingRuns}
              onClick={goToPreviousPage}
              type="button"
            >
              <LuChevronLeft size={13} aria-hidden="true" />
            </button>
            <button
              aria-label="Next page of runs"
              className="hover:bg-surface-700 hover:text-surface-100 flex h-5 w-5 items-center justify-center rounded outline-none disabled:pointer-events-none disabled:opacity-40"
              disabled={runsOffset + runs.length >= runsTotal || isRefreshingRuns}
              onClick={goToNextPage}
              type="button"
            >
              <LuChevronRight size={13} aria-hidden="true" />
            </button>
          </span>
        </div>
      ) : null}

      <ConfirmDialog
        confirmLabel="Delete"
        description={
          draftToDelete === null
            ? ""
            : `Delete ${draftToDelete.name}? Its configuration will be removed.`
        }
        onConfirm={confirmDeleteDraft}
        onOpenChange={(open) => !open && setDraftToDelete(null)}
        open={draftToDelete !== null}
        title="Delete Run"
      />
    </div>
  );
}
