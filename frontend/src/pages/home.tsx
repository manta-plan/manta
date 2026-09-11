import { Button } from "@base-ui/react/button";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { FiChevronLeft, FiChevronRight, FiPlay, FiRefreshCw, FiSearch, FiX } from "react-icons/fi";
import {
  createRun,
  getCachedDefaultProject,
  getOrCreateDefaultProject,
  getProjectRun,
  getRun,
  getRunLogs,
  getRunSummary,
  listRuns,
} from "../features/runs/api";
import { RunsTable } from "../features/runs/components/runs-table";
import { StatusFilter } from "../features/runs/components/status-filter";
import { normalizeRunStatus } from "../features/runs/status";
import type {
  DefaultProject,
  ExpandedRunState,
  GetRunResponse,
  GetRunSummaryResponse,
  RunListItem,
  RunStatus,
} from "../features/runs/types";

const runsPageSize = 10;
const emptyRunSummary: GetRunSummaryResponse = {
  total: 0,
  statuses: {},
};

export function HomePage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsOffset, setRunsOffset] = useState(0);
  const [runSummary, setRunSummary] = useState(emptyRunSummary);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isRefreshingRuns, setIsRefreshingRuns] = useState(false);
  const [runCreationError, setRunCreationError] = useState<string | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [expandedRuns, setExpandedRuns] = useState<Record<string, ExpandedRunState>>({});
  const [selectedStatuses, setSelectedStatuses] = useState<RunStatus[]>([]);
  const [searchRunId, setSearchRunId] = useState("");
  const [activeSearchRunId, setActiveSearchRunId] = useState("");

  useEffect(() => {
    const cachedProject = getCachedDefaultProject();
    let isActive = true;

    if (cachedProject === null) {
      return;
    }

    const project = cachedProject;

    async function loadInitialRuns() {
      setIsRefreshingRuns(true);
      setRunCreationError(null);

      try {
        const fetchedRuns = await listRuns(project, {
          limit: runsPageSize,
          offset: 0,
          statuses: [],
        });

        if (isActive) {
          setRuns(fetchedRuns.items.map(toRunListItem));
          setRunsTotal(fetchedRuns.total);
          setRunsOffset(fetchedRuns.offset);
          setRunSummary(fetchedRuns.summary);
        }
      } catch (error) {
        if (isActive) {
          setRunCreationError(error instanceof Error ? error.message : "Failed to refresh runs.");
        }
      } finally {
        if (isActive) {
          setIsRefreshingRuns(false);
        }
      }
    }

    void loadInitialRuns();

    return () => {
      isActive = false;
    };
  }, []);

  const hasRuns = runs.length > 0;
  const hasProjectRuns = runSummary.total > 0;
  const hasStatusFilter = selectedStatuses.length > 0;
  const hasRunSearch = activeSearchRunId.length > 0;
  const shouldShowTableArea = hasProjectRuns || hasStatusFilter || hasRunSearch;
  const pageStart = runsTotal > 0 ? runsOffset + 1 : 0;
  const pageEnd = Math.min(runsOffset + runs.length, runsTotal);
  const canGoToPreviousPage = runsOffset > 0;
  const canGoToNextPage = runsOffset + runsPageSize < runsTotal;

  const runStats = [
    {
      label: "Total Runs",
      value: String(runSummary.total),
      tone: "text-primary",
      detail: hasProjectRuns ? "tracked in this project" : "no runs yet",
    },
    {
      label: "Running",
      value: String(runSummary.statuses.RUNNING ?? 0),
      tone: "text-secondary",
      detail: hasProjectRuns ? "executing now" : "none active",
    },
    {
      label: "Completed",
      value: String(runSummary.statuses.COMPLETED ?? 0),
      tone: "text-primary",
      detail: hasProjectRuns ? "finished successfully" : "no results yet",
    },
    {
      label: "Scheduled",
      value: String(runSummary.statuses.SCHEDULED ?? 0),
      tone: "text-text",
      detail: hasProjectRuns ? "waiting to start" : "empty queue",
    },
  ];

  async function handleNewRun() {
    setIsLoadingRuns(true);
    setRunCreationError(null);

    try {
      const project = await getOrCreateDefaultProject();
      await createRun(project);

      setSearchRunId("");
      setActiveSearchRunId("");
      setRunsOffset(0);
      await refreshRunsPage(project, 0, selectedStatuses);
    } catch (error) {
      setRunCreationError(error instanceof Error ? error.message : "Failed to create run.");
    } finally {
      setIsLoadingRuns(false);
    }
  }

  async function refreshRuns(project: DefaultProject) {
    if (activeSearchRunId.length > 0) {
      await refreshRunSearch(project, activeSearchRunId);
      return;
    }

    await refreshRunsPage(project, runsOffset, selectedStatuses);
  }

  async function refreshRunsPage(project: DefaultProject, offset: number, statuses: RunStatus[]) {
    setIsRefreshingRuns(true);
    setRunCreationError(null);

    try {
      const fetchedRuns = await listRuns(project, { limit: runsPageSize, offset, statuses });
      setRuns(fetchedRuns.items.map(toRunListItem));
      setRunsTotal(fetchedRuns.total);
      setRunsOffset(fetchedRuns.offset);
      setRunSummary(fetchedRuns.summary);
    } catch (error) {
      setRunCreationError(error instanceof Error ? error.message : "Failed to refresh runs.");
    } finally {
      setIsRefreshingRuns(false);
    }
  }

  async function refreshRunDetails(runId: string) {
    setExpandedRuns((currentExpandedRuns) => ({
      ...currentExpandedRuns,
      [runId]: {
        isLoading: true,
        error: null,
        detail: currentExpandedRuns[runId]?.detail ?? null,
        logs: currentExpandedRuns[runId]?.logs ?? null,
      },
    }));

    try {
      const cachedProject = getCachedDefaultProject();
      const [detail, logs, latestRunSummary] = await Promise.all([
        getRun(runId),
        getRunLogs(runId),
        cachedProject === null ? Promise.resolve(null) : getRunSummary(cachedProject),
      ]);
      const runStatus = normalizeRunStatus(logs.run_status || detail.status);

      setRuns((currentRuns) =>
        currentRuns.map((run) =>
          run.id === runId ? { ...run, status: runStatus, startedAt: detail.created_at } : run,
        ),
      );
      setExpandedRuns((currentExpandedRuns) => ({
        ...currentExpandedRuns,
        [runId]: {
          isLoading: false,
          error: null,
          detail,
          logs,
        },
      }));
      if (latestRunSummary !== null) {
        setRunSummary(latestRunSummary);
      }
    } catch (error) {
      setExpandedRuns((currentExpandedRuns) => ({
        ...currentExpandedRuns,
        [runId]: {
          isLoading: false,
          error: error instanceof Error ? error.message : "Failed to load run details.",
          detail: currentExpandedRuns[runId]?.detail ?? null,
          logs: currentExpandedRuns[runId]?.logs ?? null,
        },
      }));
    }
  }

  async function handleToggleRunDetails(runId: string) {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }

    setExpandedRunId(runId);

    const expandedRun = expandedRuns[runId];

    if (expandedRun !== undefined && expandedRun.detail !== null && expandedRun.logs !== null) {
      return;
    }

    await refreshRunDetails(runId);
  }

  async function handleRefreshRuns() {
    const cachedProject = getCachedDefaultProject();

    if (cachedProject === null) {
      return;
    }

    await refreshRuns(cachedProject);
  }

  async function refreshRunSearch(project: DefaultProject, runId: string) {
    setIsRefreshingRuns(true);
    setRunCreationError(null);

    try {
      const [run, latestRunSummary] = await Promise.all([
        getProjectRun(project, runId),
        getRunSummary(project),
      ]);
      setRuns(run === null ? [] : [toRunListItem(run)]);
      setRunsTotal(run === null ? 0 : 1);
      setRunsOffset(0);
      setRunSummary(latestRunSummary);
    } catch (error) {
      setRunCreationError(error instanceof Error ? error.message : "Failed to search run.");
    } finally {
      setIsRefreshingRuns(false);
    }
  }

  async function handleRunSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const runId = searchRunId.trim();
    const cachedProject = getCachedDefaultProject();

    if (cachedProject === null) {
      return;
    }

    if (runId.length === 0) {
      setActiveSearchRunId("");
      setRunsOffset(0);
      await refreshRunsPage(cachedProject, 0, selectedStatuses);
      return;
    }

    setSelectedStatuses([]);
    setActiveSearchRunId(runId);
    await refreshRunSearch(cachedProject, runId);
  }

  async function handleClearRunSearch() {
    setSearchRunId("");
    setActiveSearchRunId("");

    const cachedProject = getCachedDefaultProject();

    if (cachedProject === null) {
      return;
    }

    setRunsOffset(0);
    await refreshRunsPage(cachedProject, 0, selectedStatuses);
  }

  async function handlePreviousRunsPage() {
    const cachedProject = getCachedDefaultProject();

    if (cachedProject === null) {
      return;
    }

    await refreshRunsPage(cachedProject, Math.max(runsOffset - runsPageSize, 0), selectedStatuses);
  }

  async function handleNextRunsPage() {
    const cachedProject = getCachedDefaultProject();

    if (cachedProject === null) {
      return;
    }

    await refreshRunsPage(cachedProject, runsOffset + runsPageSize, selectedStatuses);
  }

  async function handleSelectedStatusesChange(statuses: RunStatus[]) {
    setSelectedStatuses(statuses);
    setSearchRunId("");
    setActiveSearchRunId("");
    setRunsOffset(0);

    const cachedProject = getCachedDefaultProject();

    if (cachedProject === null) {
      return;
    }

    await refreshRunsPage(cachedProject, 0, statuses);
  }

  return (
    <main className="bg-background text-text min-h-svh">
      <header className="border-border bg-surface border-b">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-6 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <img
              alt="MANTA Energy"
              className="size-8 shrink-0 rounded object-contain"
              src="/manta-icon.svg"
            />
            <div className="border-border min-w-0 border-l pl-4">
              <h1 className="text-xl font-semibold tracking-normal">Runs</h1>
              <p className="text-text-secondary mt-0.5 truncate text-sm">
                Monitor recent executions and operational workflows.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
              disabled={isRefreshingRuns}
              onClick={handleRefreshRuns}
            >
              <FiRefreshCw
                className={`size-4 ${isRefreshingRuns ? "animate-spin" : ""}`}
                aria-hidden="true"
              />
              {isRefreshingRuns ? "Refreshing..." : "Refresh"}
            </Button>
            <Button
              className="bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary shadow-primary/20 inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
              disabled={isLoadingRuns}
              onClick={handleNewRun}
            >
              {isLoadingRuns ? (
                <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <FiPlay className="size-4" aria-hidden="true" />
              )}
              {isLoadingRuns ? "Starting..." : "New run"}
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-7xl gap-6 px-6 py-6">
        {runCreationError ? (
          <div className="border-border bg-surface rounded-lg border px-4 py-3 text-sm text-red-700">
            {runCreationError}
          </div>
        ) : null}

        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {runStats.map((stat) => (
            <div className="border-border bg-surface rounded-lg border px-4 py-3" key={stat.label}>
              <dt className="text-text-secondary text-sm font-medium">{stat.label}</dt>
              <dd className={`mt-2 text-3xl font-semibold tracking-normal ${stat.tone}`}>
                {stat.value}
              </dd>
              <dd className="text-text-secondary mt-1 text-sm">{stat.detail}</dd>
            </div>
          ))}
        </dl>

        <section className="border-border bg-surface overflow-hidden rounded-lg border shadow-sm">
          <div className="border-border flex flex-col gap-3 border-b px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-base font-semibold tracking-normal">Recent runs</h2>
              <p className="text-text-secondary mt-1 text-sm">
                Latest execution activity across active MANTA workflows.
              </p>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <form
                className="border-border bg-surface-alt text-text-secondary flex h-10 min-w-64 items-center gap-2 rounded-md border px-3 text-sm"
                onSubmit={handleRunSearchSubmit}
              >
                <FiSearch className="size-4" aria-hidden="true" />
                <label className="sr-only" htmlFor="run-search">
                  Search by run UUID
                </label>
                <input
                  className="placeholder:text-muted text-text min-w-0 flex-1 bg-transparent outline-none"
                  id="run-search"
                  onChange={(event) => setSearchRunId(event.target.value)}
                  placeholder="Search by run UUID"
                  value={searchRunId}
                  type="search"
                />
                {searchRunId.length > 0 ? (
                  <Button
                    aria-label="Clear run search"
                    className="hover:bg-surface focus-visible:outline-secondary text-text-secondary inline-flex size-6 items-center justify-center rounded transition focus-visible:outline-2 focus-visible:outline-offset-2"
                    onClick={handleClearRunSearch}
                    type="button"
                  >
                    <FiX className="size-4" aria-hidden="true" />
                  </Button>
                ) : null}
              </form>
              <StatusFilter
                selectedStatuses={selectedStatuses}
                onSelectedStatusesChange={handleSelectedStatusesChange}
              />
            </div>
          </div>

          {shouldShowTableArea ? (
            hasRuns ? (
              <RunsTable
                runs={runs}
                expandedRunId={expandedRunId}
                expandedRuns={expandedRuns}
                onRefreshRunDetails={refreshRunDetails}
                onToggleRunDetails={handleToggleRunDetails}
              />
            ) : (
              <div className="grid min-h-72 place-items-center px-6 py-12 text-center">
                <div className="max-w-sm">
                  <div className="bg-surface-alt text-primary mx-auto mb-4 flex size-12 items-center justify-center rounded-lg">
                    <FiSearch className="size-5" aria-hidden="true" />
                  </div>
                  <h3 className="text-lg font-semibold tracking-normal">
                    {hasRunSearch ? "No run found" : "No matching runs"}
                  </h3>
                  <p className="text-text-secondary mt-2 text-sm leading-6">
                    {hasRunSearch
                      ? "Check the run UUID and try again."
                      : "Adjust the status filter to bring more executions back into view."}
                  </p>
                </div>
              </div>
            )
          ) : (
            <div className="grid min-h-72 place-items-center px-6 py-12 text-center">
              <div className="max-w-sm">
                <div className="bg-surface-alt text-primary mx-auto mb-4 flex size-12 items-center justify-center rounded-lg">
                  {isLoadingRuns ? (
                    <FiRefreshCw className="size-5 animate-spin" aria-hidden="true" />
                  ) : (
                    <FiPlay className="size-5" aria-hidden="true" />
                  )}
                </div>
                <h3 className="text-lg font-semibold tracking-normal">
                  {isLoadingRuns ? "Starting run" : "No runs yet"}
                </h3>
                <p className="text-text-secondary mt-2 text-sm leading-6">
                  {isLoadingRuns
                    ? "Preparing execution for this workspace."
                    : "Create a run to populate this workspace with execution activity."}
                </p>
              </div>
            </div>
          )}
          {shouldShowTableArea ? (
            <div className="border-border flex flex-col gap-3 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-text-secondary text-sm">
                {hasRunSearch
                  ? `Search result for ${activeSearchRunId}`
                  : `Showing ${pageStart}-${pageEnd} of ${runsTotal}`}
              </p>
              {hasRunSearch ? null : (
                <div className="flex items-center gap-2">
                  <Button
                    className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!canGoToPreviousPage || isRefreshingRuns}
                    onClick={handlePreviousRunsPage}
                  >
                    <FiChevronLeft className="size-4" aria-hidden="true" />
                    Previous
                  </Button>
                  <Button
                    className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!canGoToNextPage || isRefreshingRuns}
                    onClick={handleNextRunsPage}
                  >
                    Next
                    <FiChevronRight className="size-4" aria-hidden="true" />
                  </Button>
                </div>
              )}
            </div>
          ) : null}
        </section>
      </section>
    </main>
  );
}

function toRunListItem(run: GetRunResponse): RunListItem {
  return {
    id: run.uuid,
    name: "Pi digit statistics",
    playbook: "Pi Digit Statistics",
    status: normalizeRunStatus(run.status),
    startedAt: run.created_at,
    durationSeconds: null,
    trigger: "Manual",
    owner: "Guest",
  };
}
