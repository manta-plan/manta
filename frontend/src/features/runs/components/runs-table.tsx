// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Button } from "@base-ui/react/button";
import { Fragment } from "react";
import { FiChevronDown } from "react-icons/fi";
import { Link, useParams } from "wouter";
import { projectRunHref } from "../../project/lib/project-route";
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
  const { projectId } = useParams<{ projectId: string }>();

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] border-collapse text-left text-[12px]">
        <thead className="bg-surface-800 text-surface-400">
          <tr>
            <th className="px-4 py-2 font-semibold">Run</th>
            <th className="px-4 py-2 font-semibold">Status</th>
            <th className="px-4 py-2 font-semibold">Started</th>
            <th className="px-4 py-2 font-semibold">Duration</th>
            <th className="px-4 py-2 font-semibold">Trigger</th>
            <th className="px-4 py-2 font-semibold">Owner</th>
            <th className="px-4 py-2 text-right font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-surface-700 divide-y">
          {runs.map((run) => {
            const isExpanded = expandedRunId === run.id;
            const expandedRun = expandedRuns[run.id];

            return (
              <Fragment key={run.id}>
                <tr className="hover:bg-surface-800/70 transition">
                  <td className="px-4 py-3">
                    <Link
                      className="text-surface-50 hover:text-accent-300 focus-visible:outline-accent-400 font-semibold focus-visible:outline-2"
                      href={projectRunHref(projectId, run.id)}
                    >
                      {run.name}
                    </Link>
                    <div className="text-surface-400 mt-1 flex items-center gap-2">
                      <span>{run.id}</span>
                      <span aria-hidden="true">/</span>
                      <span>{run.playbook}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <RunStatusBadge status={run.status} />
                  </td>
                  <td className="text-surface-300 px-4 py-3">
                    {formatRunStartedAt(run.startedAt)}
                  </td>
                  <td className="text-surface-300 px-4 py-3">
                    {formatRunDuration(run.durationSeconds)}
                  </td>
                  <td className="text-surface-300 px-4 py-3">{run.trigger}</td>
                  <td className="text-surface-300 px-4 py-3">{run.owner}</td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      aria-expanded={isExpanded}
                      aria-label={`${isExpanded ? "Collapse" : "Expand"} details for ${run.name}`}
                      className="hover:bg-surface-700 focus-visible:outline-accent-400 text-surface-400 inline-flex size-8 items-center justify-center rounded transition focus-visible:outline-2 focus-visible:outline-offset-2"
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
                  <tr className="bg-surface-800/40">
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
