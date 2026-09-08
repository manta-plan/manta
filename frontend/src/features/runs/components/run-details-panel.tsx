import { Button } from "@base-ui/react/button";
import { FiRefreshCw } from "react-icons/fi";
import type { ExpandedRunState } from "../types";

type RunDetailsPanelProps = {
  state: ExpandedRunState | undefined;
  onRefresh: () => void;
};

export function RunDetailsPanel({ state, onRefresh }: RunDetailsPanelProps) {
  if (state === undefined || (state.isLoading && (state.detail === null || state.logs === null))) {
    return (
      <div className="text-text-secondary flex items-center gap-2 text-sm">
        <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
        Loading run details...
      </div>
    );
  }

  if (state.error !== null) {
    return (
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm text-red-700">{state.error}</div>
        <Button
          aria-label="Retry run details refresh"
          className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-8 items-center gap-2 rounded-md border px-2.5 text-xs font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2"
          onClick={onRefresh}
        >
          <FiRefreshCw className="size-3.5" aria-hidden="true" />
          Retry
        </Button>
      </div>
    );
  }

  const detail = state.detail;
  const logs = state.logs;

  if (detail === null || logs === null) {
    return null;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <dl className="grid gap-3 text-sm sm:grid-cols-3 lg:grid-cols-1">
        <div>
          <dt className="text-text-secondary">Run UUID</dt>
          <dd className="mt-1 font-medium break-all">{detail.uuid}</dd>
        </div>
        <div>
          <dt className="text-text-secondary">Project UUID</dt>
          <dd className="mt-1 font-medium break-all">{detail.project_uuid ?? "-"}</dd>
        </div>
        <div>
          <dt className="text-text-secondary">Backend status</dt>
          <dd className="mt-1 font-medium">{detail.status}</dd>
        </div>
      </dl>

      <section>
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Logs</h3>
          <Button
            aria-label="Refresh run details"
            className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-8 items-center gap-2 rounded-md border px-2.5 text-xs font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2"
            disabled={state.isLoading}
            onClick={onRefresh}
          >
            <FiRefreshCw
              className={`size-3.5 ${state.isLoading ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            {state.isLoading ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
        {logs.logs.length > 0 ? (
          <pre className="bg-text text-background mt-2 max-h-56 overflow-auto rounded-md p-3 text-xs leading-5">
            {logs.logs.join("\n")}
          </pre>
        ) : (
          <p className="text-text-secondary mt-2 text-sm">No logs are available yet.</p>
        )}
      </section>
    </div>
  );
}
