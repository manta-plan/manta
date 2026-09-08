import { Button } from "@base-ui/react/button";
import { Fragment } from "react";
import { FiChevronDown } from "react-icons/fi";
import type { ExpandedRunState, RunListItem } from "../types";
import { formatRunDuration, formatRunStartedAt } from "../utils";
import { RunDetailsPanel } from "./run-details-panel";
import { RunStatusBadge } from "./run-status-badge";

type RunsTableProps = {
  runs: RunListItem[];
  expandedRunId: string | null;
  expandedRuns: Record<string, ExpandedRunState>;
  onRefreshRunDetails: (runId: string) => void;
  onToggleRunDetails: (runId: string) => void;
};

export function RunsTable({
  runs,
  expandedRunId,
  expandedRuns,
  onRefreshRunDetails,
  onToggleRunDetails,
}: RunsTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] border-collapse text-left text-sm">
        <thead className="bg-surface-alt text-text-secondary">
          <tr>
            <th className="px-4 py-3 font-semibold">Run</th>
            <th className="px-4 py-3 font-semibold">Status</th>
            <th className="px-4 py-3 font-semibold">Started</th>
            <th className="px-4 py-3 font-semibold">Duration</th>
            <th className="px-4 py-3 font-semibold">Trigger</th>
            <th className="px-4 py-3 font-semibold">Owner</th>
            <th className="px-4 py-3 text-right font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-border divide-y">
          {runs.map((run) => {
            const isExpanded = expandedRunId === run.id;
            const expandedRun = expandedRuns[run.id];

            return (
              <Fragment key={run.id}>
                <tr className="hover:bg-surface-alt/70 transition">
                  <td className="px-4 py-4">
                    <div className="text-text font-semibold">{run.name}</div>
                    <div className="text-text-secondary mt-1 flex items-center gap-2">
                      <span>{run.id}</span>
                      <span aria-hidden="true">/</span>
                      <span>{run.playbook}</span>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <RunStatusBadge status={run.status} />
                  </td>
                  <td className="text-text-secondary px-4 py-4">
                    {formatRunStartedAt(run.startedAt)}
                  </td>
                  <td className="text-text-secondary px-4 py-4">
                    {formatRunDuration(run.durationSeconds)}
                  </td>
                  <td className="text-text-secondary px-4 py-4">{run.trigger}</td>
                  <td className="text-text-secondary px-4 py-4">{run.owner}</td>
                  <td className="px-4 py-4 text-right">
                    <Button
                      aria-expanded={isExpanded}
                      aria-label={`${isExpanded ? "Collapse" : "Expand"} details for ${run.name}`}
                      className="hover:bg-surface-alt focus-visible:outline-secondary text-text-secondary inline-flex size-8 items-center justify-center rounded-md transition focus-visible:outline-2 focus-visible:outline-offset-2"
                      onClick={() => onToggleRunDetails(run.id)}
                    >
                      <FiChevronDown
                        className={`size-4 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                        aria-hidden="true"
                      />
                    </Button>
                  </td>
                </tr>
                {isExpanded ? (
                  <tr className="bg-surface-alt/40">
                    <td className="px-4 py-4" colSpan={7}>
                      <RunDetailsPanel
                        state={expandedRun}
                        onRefresh={() => onRefreshRunDetails(run.id)}
                      />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
