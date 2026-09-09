import { Button } from "@base-ui/react/button";
import { useEffect, useState } from "react";
import { FiPlay, FiRefreshCw, FiSearch } from "react-icons/fi";
import {
  createRun,
  getCachedDefaultProject,
  getOrCreateDefaultProject,
  getRun,
  getRunLogs,
  listRuns,
} from "../features/runs/api";
import { RunsTable } from "../features/runs/components/runs-table";
import { StatusFilter } from "../features/runs/components/status-filter";
import { normalizeRunStatus } from "../features/runs/status";
import type {
  DefaultProject,
  ExpandedRunState,
  GetRunResponse,
  RunListItem,
  RunStatus,
} from "../features/runs/types";

export function HomePage() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isRefreshingRuns, setIsRefreshingRuns] = useState(false);
  const [runCreationError, setRunCreationError] = useState<string | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [expandedRuns, setExpandedRuns] = useState<Record<string, ExpandedRunState>>({});
  const [selectedStatuses, setSelectedStatuses] = useState<RunStatus[]>([]);

  useEffect(() => {
    const cachedProject = getCachedDefaultProject();

    if (cachedProject === null) {
      return;
    }

    void refreshRuns(cachedProject);
  }, []);

  const hasRuns = runs.length > 0;
  const filteredRuns =
    selectedStatuses.length > 0
      ? runs.filter((run) => selectedStatuses.includes(run.status))
      : runs;

  const runStats = [
    {
      label: "Running",
      value: String(runs.filter((run) => run.status === "Running").length),
      tone: "text-secondary",
      detail: hasRuns ? "active simulations" : "no active runs",
    },
    {
      label: "Completed",
      value: String(runs.filter((run) => run.status === "Completed").length),
      tone: "text-primary",
      detail: hasRuns ? "ready to inspect" : "no results yet",
    },
    {
      label: "Failed",
      value: String(runs.filter((run) => run.status === "Failed").length),
      tone: "text-red-600",
      detail: hasRuns ? "needs review" : "clear",
    },
    {
      label: "Queued",
      value: String(runs.filter((run) => run.status === "Queued").length),
      tone: "text-text",
      detail: hasRuns ? "waiting for workers" : "empty queue",
    },
  ];

  async function handleNewRun() {
    setIsLoadingRuns(true);
    setRunCreationError(null);

    try {
      const project = await getOrCreateDefaultProject();
      const run = await createRun(project);

      setRuns((currentRuns) => [
        {
          id: run.uuid,
          name: "Pi digit statistics",
          playbook: "Pi Digit Statistics",
          status: "Queued",
          startedAt: run.created_at,
          durationSeconds: null,
          trigger: "Manual",
          owner: "Guest",
        },
        ...currentRuns,
      ]);
    } catch (error) {
      setRunCreationError(error instanceof Error ? error.message : "Failed to create run.");
    } finally {
      setIsLoadingRuns(false);
    }
  }

  async function refreshRuns(project: DefaultProject) {
    setIsRefreshingRuns(true);
    setRunCreationError(null);

    try {
      const fetchedRuns = await listRuns(project);
      setRuns(fetchedRuns.map(toRunListItem));
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
      const [detail, logs] = await Promise.all([getRun(runId), getRunLogs(runId)]);
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
              <label className="border-border bg-surface-alt text-text-secondary flex h-10 min-w-64 items-center gap-2 rounded-md border px-3 text-sm">
                <FiSearch className="size-4" aria-hidden="true" />
                <span className="sr-only">Search runs</span>
                <input
                  className="placeholder:text-muted text-text min-w-0 flex-1 bg-transparent outline-none"
                  placeholder="Search runs"
                  type="search"
                />
              </label>
              <StatusFilter
                selectedStatuses={selectedStatuses}
                onSelectedStatusesChange={setSelectedStatuses}
              />
            </div>
          </div>

          {hasRuns ? (
            filteredRuns.length > 0 ? (
              <RunsTable
                runs={filteredRuns}
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
                  <h3 className="text-lg font-semibold tracking-normal">No matching runs</h3>
                  <p className="text-text-secondary mt-2 text-sm leading-6">
                    Adjust the status filter to bring more executions back into view.
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
                  {isLoadingRuns ? "Starting demo run" : "No runs yet"}
                </h3>
                <p className="text-text-secondary mt-2 text-sm leading-6">
                  {isLoadingRuns
                    ? "Preparing sample executions for the workspace."
                    : "Create a run to populate this workspace with execution activity."}
                </p>
              </div>
            </div>
          )}
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
