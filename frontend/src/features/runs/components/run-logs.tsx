// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Button } from "@base-ui/react/button";
import { FiRefreshCw } from "react-icons/fi";
import type { ExpandedRunState } from "../types";

type RunLogsSectionProps = {
  state: ExpandedRunState;
  onRefresh: () => void;
  /** Where the lines are shown; the table row caps their height. */
  logClassName: string;
};

// The log of a run with its Refresh button, shared by the table row and the run workspace.
export function RunLogsSection({ state, onRefresh, logClassName }: RunLogsSectionProps) {
  const lines = state.logs?.logs ?? [];

  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">Logs</h3>
        <Button
          aria-label="Refresh run details"
          className="border-surface-600 text-surface-200 hover:bg-surface-700 focus-visible:outline-accent-400 inline-flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={state.isLoading}
          onClick={onRefresh}
        >
          <FiRefreshCw
            className={`size-3 ${state.isLoading ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          {state.isLoading ? "Refreshing..." : "Refresh"}
        </Button>
      </div>
      {lines.length > 0 ? (
        <pre
          className={`bg-surface-950 text-surface-300 mt-2 overflow-auto rounded p-3 font-mono text-[11px] leading-5 ${logClassName}`}
        >
          {lines.join("\n")}
        </pre>
      ) : (
        <p className="text-surface-400 mt-2 text-[12px]">No logs are available yet.</p>
      )}
    </section>
  );
}
