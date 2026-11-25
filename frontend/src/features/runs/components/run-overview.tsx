// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Button } from "@base-ui/react/button";
import { FiPlay, FiRefreshCw } from "react-icons/fi";
import { LuArrowRight, LuCirclePlay, LuGitCommitVertical, LuWorkflow } from "react-icons/lu";
import { useProjectStore } from "../../project/store/project-store";
import { summarizeRunStatuses } from "../status-groups";
import { useRunsStore } from "../store/runs-store";
import { useOpenNewRun } from "../use-open-new-run";
import { listRecordScenarios } from "../list-record-scenarios";
import { RecentRuns } from "./recent-runs";
import {
  OverviewEmptyStats,
  OverviewSectionHeader,
  OverviewStat,
  OverviewStatGrid,
} from "./workspace-overview-parts";

const conceptClassName = "min-h-36 px-5 py-4";
const conceptTitleClassName = "text-surface-100 flex items-center gap-2 text-[12px] font-medium";
const conceptTextClassName = "text-surface-400 mt-2 text-[12px] leading-5";
const conceptCountClassName = "text-surface-200 mt-3 text-[11px] font-medium";

function HowRunsWork() {
  const record = useProjectStore((s) => s.record);
  const playbooksCount = useRunsStore((s) => s.playbooks.length);
  const playbooksStatus = useRunsStore((s) => s.playbooksStatus);
  const runsCount = useRunsStore((s) => s.runSummary.total);
  const scenariosCount = record === null ? 0 : listRecordScenarios(record.info.revisions).length;

  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title="How Runs Work" />
      <div className="divide-surface-700 grid divide-y lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:divide-x lg:divide-y-0">
        <div className={conceptClassName}>
          <div className={conceptTitleClassName}>
            <LuGitCommitVertical className="text-accent-400" size={15} aria-hidden="true" />
            Scenario
          </div>
          <p className={conceptTextClassName}>
            A scenario is a variant of the record. It is the input a run starts from.
          </p>
          <div className={conceptCountClassName}>{scenariosCount} available scenarios</div>
        </div>
        <div className="text-surface-500 hidden items-center justify-center px-3 lg:flex">
          <LuArrowRight size={15} aria-hidden="true" />
        </div>
        <div className={conceptClassName}>
          <div className={conceptTitleClassName}>
            <LuWorkflow className="text-warn-500" size={15} aria-hidden="true" />
            Playbook
          </div>
          <p className={conceptTextClassName}>
            A playbook defines the model workflow: the blocks to run and their settings.
          </p>
          <div className={conceptCountClassName}>
            {playbooksStatus === "ready"
              ? `${playbooksCount} available playbooks`
              : "Loading playbooks..."}
          </div>
        </div>
        <div className="text-surface-500 hidden items-center justify-center px-3 lg:flex">
          <LuArrowRight size={15} aria-hidden="true" />
        </div>
        <div className={conceptClassName}>
          <div className={conceptTitleClassName}>
            <LuCirclePlay className="text-ok-500" size={15} aria-hidden="true" />
            Run
          </div>
          <p className={conceptTextClassName}>
            A run executes one playbook on one data record and keeps its logs.
          </p>
          <div className={conceptCountClassName}>{runsCount} existing runs</div>
        </div>
      </div>
    </section>
  );
}

function RunStatistics({ draftCount }: { draftCount: number }) {
  const runSummary = useRunsStore((s) => s.runSummary);
  const counts = summarizeRunStatuses(runSummary);

  return (
    <OverviewStatGrid title="Run Statistics">
      <OverviewStat
        detail={draftCount > 0 ? `${draftCount} draft` : undefined}
        label="Total Runs"
        value={counts.total}
      />
      <OverviewStat
        detail={counts.successRate === null ? undefined : `${counts.successRate}% success rate`}
        label="Succeeded"
        value={counts.succeeded}
      />
      <OverviewStat label="In Progress" value={counts.inProgress} />
      <OverviewStat label="Failed" value={counts.failed} />
    </OverviewStatGrid>
  );
}

// Shown when no run is open: the statistics, the concept, and the table of runs.
export function RunOverview({ projectId }: { projectId: string }) {
  const openNewRun = useOpenNewRun();
  const hasProjectRuns = useRunsStore((s) => s.runSummary.total > 0);
  const draftCount = useRunsStore(
    (s) => s.drafts.filter((draft) => draft.projectId === projectId).length,
  );
  const isRefreshingRuns = useRunsStore((s) => s.isRefreshingRuns);
  const runsError = useRunsStore((s) => s.runsError);
  const refresh = useRunsStore((s) => s.refresh);

  return (
    <div className="bg-surface-900 text-surface-50 flex h-full flex-col overflow-y-auto">
      <header className="border-surface-700 flex h-14 shrink-0 items-center justify-between gap-3 border-b px-5">
        <div className="min-w-0">
          <h1 className="text-surface-50 text-[14px] font-semibold">Run Workspace</h1>
          <p className="text-surface-400 mt-0.5 truncate text-[11px]">
            Configure and execute a repeatable model workflow.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            className="border-surface-600 text-surface-200 hover:bg-surface-700 focus-visible:outline-accent-400 inline-flex h-8 items-center gap-1.5 rounded border px-3 text-[12px] font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isRefreshingRuns}
            onClick={() => void refresh()}
          >
            <FiRefreshCw
              className={`size-3.5 ${isRefreshingRuns ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            {isRefreshingRuns ? "Refreshing..." : "Refresh"}
          </Button>
          <Button
            className="bg-accent-600 hover:bg-accent-500 focus-visible:outline-accent-300 inline-flex h-8 items-center gap-1.5 rounded px-3 text-[12px] font-medium text-white transition focus-visible:outline-2 focus-visible:outline-offset-2"
            onClick={() => openNewRun()}
          >
            <FiPlay className="size-3.5" aria-hidden="true" />
            New run
          </Button>
        </div>
      </header>

      {runsError ? (
        <div
          className="border-surface-700 border-b bg-red-500/10 px-5 py-3 text-[12px] text-red-300"
          role="alert"
        >
          {runsError}
        </div>
      ) : null}

      {/* Returning users care about run status first; first-timers need the concept first. */}
      {hasProjectRuns || draftCount > 0 ? (
        <>
          <RunStatistics draftCount={draftCount} />
          <HowRunsWork />
        </>
      ) : (
        <>
          <HowRunsWork />
          <OverviewEmptyStats
            action={{ label: "New Run", onClick: () => openNewRun() }}
            message="No runs yet. Create one to execute a playbook on a data record."
            title="Run Statistics"
          />
        </>
      )}

      <RecentRuns />
    </div>
  );
}
