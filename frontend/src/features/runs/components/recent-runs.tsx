// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { Button } from "@base-ui/react/button";
import type { FormEvent } from "react";
import { FiChevronLeft, FiChevronRight, FiPlay, FiRefreshCw, FiSearch, FiX } from "react-icons/fi";
import { runsPageSize, useRunsStore } from "../store/runs-store";
import { OverviewSectionHeader } from "./workspace-overview-parts";
import { RunsTable } from "./runs-table";

const secondaryButtonClassName =
  "border-surface-600 text-surface-200 hover:bg-surface-700 focus-visible:outline-accent-400 inline-flex h-8 items-center gap-1.5 rounded border px-3 text-[12px] font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

// The runs of the backend as a table: search by UUID, status filter (set in the sidebar),
// expandable details and paging.
export function RecentRuns() {
  const runs = useRunsStore((s) => s.runs);
  const runsTotal = useRunsStore((s) => s.runsTotal);
  const runsOffset = useRunsStore((s) => s.runsOffset);
  const runSummary = useRunsStore((s) => s.runSummary);
  const isRefreshingRuns = useRunsStore((s) => s.isRefreshingRuns);
  const selectedStatuses = useRunsStore((s) => s.selectedStatuses);
  const searchRunId = useRunsStore((s) => s.searchRunId);
  const activeSearchRunId = useRunsStore((s) => s.activeSearchRunId);
  const expandedRunId = useRunsStore((s) => s.expandedRunId);
  const expandedRuns = useRunsStore((s) => s.expandedRuns);
  const setSearchRunId = useRunsStore((s) => s.setSearchRunId);
  const submitSearch = useRunsStore((s) => s.submitSearch);
  const clearSearch = useRunsStore((s) => s.clearSearch);
  const refreshRunDetails = useRunsStore((s) => s.refreshRunDetails);
  const toggleRunDetails = useRunsStore((s) => s.toggleRunDetails);
  const goToPreviousPage = useRunsStore((s) => s.goToPreviousPage);
  const goToNextPage = useRunsStore((s) => s.goToNextPage);

  const hasRuns = runs.length > 0;
  const hasProjectRuns = runSummary.total > 0;
  const hasRunSearch = activeSearchRunId.length > 0;
  const shouldShowTableArea = hasProjectRuns || selectedStatuses.length > 0 || hasRunSearch;
  const pageStart = runsTotal > 0 ? runsOffset + 1 : 0;
  const pageEnd = Math.min(runsOffset + runs.length, runsTotal);

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitSearch();
  }

  return (
    <section>
      <OverviewSectionHeader title="Recent runs">
        <form
          className="border-surface-600 bg-surface-800 text-surface-400 flex h-7 min-w-64 items-center gap-2 rounded border px-2 text-[12px]"
          onSubmit={handleSearchSubmit}
        >
          <FiSearch className="size-3.5" aria-hidden="true" />
          <label className="sr-only" htmlFor="run-search">
            Search by run UUID
          </label>
          <input
            className="placeholder:text-surface-500 text-surface-50 min-w-0 flex-1 bg-transparent outline-none"
            id="run-search"
            onChange={(event) => setSearchRunId(event.target.value)}
            placeholder="Search by run UUID"
            type="search"
            value={searchRunId}
          />
          {searchRunId.length > 0 ? (
            <Button
              aria-label="Clear run search"
              className="hover:bg-surface-700 focus-visible:outline-accent-400 text-surface-400 inline-flex size-5 items-center justify-center rounded transition focus-visible:outline-2"
              onClick={() => void clearSearch()}
              type="button"
            >
              <FiX className="size-3.5" aria-hidden="true" />
            </Button>
          ) : null}
        </form>
      </OverviewSectionHeader>

      {shouldShowTableArea ? (
        hasRuns ? (
          <RunsTable
            expandedRunId={expandedRunId}
            expandedRuns={expandedRuns}
            onRefreshRunDetails={(runId) => void refreshRunDetails(runId)}
            onToggleRunDetails={(runId) => void toggleRunDetails(runId)}
            runs={runs}
          />
        ) : (
          <div className="grid min-h-60 place-items-center px-6 py-10 text-center">
            <div className="max-w-sm">
              <div className="bg-surface-800 text-accent-400 mx-auto mb-3 flex size-10 items-center justify-center rounded-lg">
                <FiSearch className="size-5" aria-hidden="true" />
              </div>
              <h3 className="text-surface-50 text-[14px] font-semibold">
                {hasRunSearch ? "No run found" : "No matching runs"}
              </h3>
              <p className="text-surface-400 mt-2 text-[12px] leading-5">
                {hasRunSearch
                  ? "Check the run UUID and try again."
                  : "Adjust the run filters to bring more executions back into view."}
              </p>
            </div>
          </div>
        )
      ) : (
        <div className="grid min-h-60 place-items-center px-6 py-10 text-center">
          <div className="max-w-sm">
            <div className="bg-surface-800 text-accent-400 mx-auto mb-3 flex size-10 items-center justify-center rounded-lg">
              {isRefreshingRuns ? (
                <FiRefreshCw className="size-5 animate-spin" aria-hidden="true" />
              ) : (
                <FiPlay className="size-5" aria-hidden="true" />
              )}
            </div>
            <h3 className="text-surface-50 text-[14px] font-semibold">
              {isRefreshingRuns ? "Loading runs" : "No runs yet"}
            </h3>
            <p className="text-surface-400 mt-2 text-[12px] leading-5">
              {isRefreshingRuns
                ? "Fetching the runs of this workspace."
                : "Create a run to populate this workspace with execution activity."}
            </p>
          </div>
        </div>
      )}

      {shouldShowTableArea ? (
        <div className="border-surface-700 flex flex-col gap-3 border-t px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-surface-400 text-[12px]">
            {hasRunSearch
              ? `Search result for ${activeSearchRunId}`
              : `Showing ${pageStart}-${pageEnd} of ${runsTotal}`}
          </p>
          {hasRunSearch ? null : (
            <div className="flex items-center gap-2">
              <Button
                className={secondaryButtonClassName}
                disabled={runsOffset <= 0 || isRefreshingRuns}
                onClick={() => void goToPreviousPage()}
              >
                <FiChevronLeft className="size-4" aria-hidden="true" />
                Previous
              </Button>
              <Button
                className={secondaryButtonClassName}
                disabled={runsOffset + runsPageSize >= runsTotal || isRefreshingRuns}
                onClick={() => void goToNextPage()}
              >
                Next
                <FiChevronRight className="size-4" aria-hidden="true" />
              </Button>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
