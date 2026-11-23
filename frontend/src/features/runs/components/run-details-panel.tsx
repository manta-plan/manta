// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { Button } from "@base-ui/react/button";
import { FiRefreshCw } from "react-icons/fi";
import type { ExpandedRunState } from "../types";
import { RunLogsSection } from "./run-logs";

type RunDetailsPanelProps = {
  state: ExpandedRunState | undefined;
  onRefresh: () => void;
};

export function RunDetailsPanel({ state, onRefresh }: RunDetailsPanelProps) {
  if (state === undefined || (state.isLoading && (state.detail === null || state.logs === null))) {
    return (
      <div className="text-surface-400 flex items-center gap-2 text-[12px]">
        <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
        Loading run details...
      </div>
    );
  }

  if (state.error !== null) {
    return (
      <div className="flex items-center justify-between gap-3">
        <div className="text-[12px] text-red-300" role="alert">
          {state.error}
        </div>
        <Button
          aria-label="Retry run details refresh"
          className="border-surface-600 text-surface-200 hover:bg-surface-700 focus-visible:outline-accent-400 inline-flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2"
          onClick={onRefresh}
        >
          <FiRefreshCw className="size-3" aria-hidden="true" />
          Retry
        </Button>
      </div>
    );
  }

  const detail = state.detail;

  if (detail === null || state.logs === null) {
    return null;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <dl className="grid gap-3 text-[12px] sm:grid-cols-3 lg:grid-cols-1">
        <div>
          <dt className="text-surface-400">Run UUID</dt>
          <dd className="text-surface-50 mt-1 font-medium break-all">{detail.uuid}</dd>
        </div>
        <div>
          <dt className="text-surface-400">Project UUID</dt>
          <dd className="text-surface-50 mt-1 font-medium break-all">{detail.project_uuid}</dd>
        </div>
        <div>
          <dt className="text-surface-400">Backend status</dt>
          <dd className="text-surface-50 mt-1 font-medium">{detail.status}</dd>
        </div>
      </dl>

      <RunLogsSection logClassName="max-h-56" onRefresh={onRefresh} state={state} />
    </div>
  );
}
