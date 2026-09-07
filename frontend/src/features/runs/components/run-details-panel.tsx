import { FiRefreshCw } from "react-icons/fi";
import type { ExpandedRunState } from "../types";

type RunDetailsPanelProps = {
  state: ExpandedRunState | undefined;
};

export function RunDetailsPanel({ state }: RunDetailsPanelProps) {
  if (state === undefined || state.isLoading) {
    return (
      <div className="text-text-secondary flex items-center gap-2 text-sm">
        <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
        Loading run details...
      </div>
    );
  }

  if (state.error !== null) {
    return <div className="text-sm text-red-700">{state.error}</div>;
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
        <h3 className="text-sm font-semibold">Logs</h3>
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
