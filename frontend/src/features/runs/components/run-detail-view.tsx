import { useEffect, type ReactNode } from "react";
import { FiRefreshCw } from "react-icons/fi";
import { LuArrowLeft, LuCircleDashed, LuCirclePlay } from "react-icons/lu";
import { Link, useLocation } from "wouter";
import { isObject } from "../../../utils/jsonObject";
import type { PlaybookConfig, PlaybookDetail, PlaybookStep } from "../../../utils/playbookTypes";
import { isStepActive } from "../../playbook-config/conditions";
import { projectRunHref } from "../../project/lib/project-route";
import { useProjectStore } from "../../project/store/project-store";
import { describeStepErrors, getActiveSteps, getStepErrors } from "../run-draft";
import { normalizeRunStatus } from "../status";
import { useRunsStore } from "../store/runs-store";
import type { RunDraft } from "../types";
import { useSelectedRun } from "../use-selected-run";
import { formatRunStartedAt } from "../utils";
import { RunFlowSnapshot } from "./run-flow-snapshot";
import type { RunFlowNodeStatus } from "./run-flow-node";
import { RunLogsSection } from "./run-logs";
import { RunStatusBadge } from "./run-status-badge";

// How long an error message stays on screen.
const messageVisibilityMs = 10_000;
// The run logs refresh at this interval until the run is finished.
const logsRefreshMs = 10_000;

const cardLabelClassName = "text-surface-400 text-[11px] font-semibold tracking-wide uppercase";

function InputRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-surface-400 shrink-0">{label}</dt>
      <dd
        className={`text-surface-100 truncate text-right ${mono ? "font-mono" : ""}`}
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

// The backend gives a state per run, not per block: every block shows the run's state.
function toNodeStatus(status: string): RunFlowNodeStatus {
  switch (normalizeRunStatus(status)) {
    case "COMPLETED":
      return "done";
    case "FAILED":
    case "CRASHED":
      return "failed";
    case "RUNNING":
      return "running";
    default:
      return "idle";
  }
}

// What a started run ran: with the settings it was started with, the steps that were active;
// without them, the steps that need no setting to run.
function getRunSteps(detail: PlaybookDetail, config: PlaybookConfig | null): PlaybookStep[] {
  return config === null
    ? detail.steps.filter((step) => step.when === null)
    : detail.steps.filter((step) => isStepActive(step, config));
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="text-surface-400 flex h-full items-center justify-center gap-2 p-6 text-center text-[12px]">
      {children}
    </div>
  );
}

function BackLink({ projectId }: { projectId: string }) {
  return (
    <Link
      className="text-surface-300 hover:text-surface-50 focus-visible:outline-accent-400 inline-flex items-center gap-1.5 text-[12px] focus-visible:outline-2"
      href={projectRunHref(projectId)}
    >
      <LuArrowLeft size={13} aria-hidden="true" />
      Run Workspace
    </Link>
  );
}

// A run opened from the sidebar or the table: a draft to review and start, or a run of the
// backend with its flow and logs.
export function RunDetailView({ runId, projectId }: { runId: string; projectId: string }) {
  const [, navigate] = useLocation();
  const selected = useSelectedRun(runId);
  const lookUpRun = useRunsStore((s) => s.lookUpRun);
  const refreshRunDetails = useRunsStore((s) => s.refreshRunDetails);
  const loadPlaybookDetail = useRunsStore((s) => s.loadPlaybookDetail);
  const startDraft = useRunsStore((s) => s.startDraft);
  const clearStartError = useRunsStore((s) => s.clearStartError);
  const startingDraftId = useRunsStore((s) => s.startingDraftId);
  const startPhase = useRunsStore((s) => s.startPhase);
  const startError = useRunsStore((s) => s.startError);
  const startIssues = useRunsStore((s) => s.startIssues);
  const expanded = useRunsStore((s) => s.expandedRuns[runId]);
  const closeRunNodeConfigDrawer = useProjectStore((s) => s.closeRunNodeConfigDrawer);
  const configuringRunNodeId = useProjectStore((s) => s.configuringRunNodeId);
  const openRunNodeConfigDrawer = useProjectStore((s) => s.openRunNodeConfigDrawer);

  const kind = selected?.kind;
  const playbookName =
    selected?.kind === "draft"
      ? selected.draft.playbook
      : selected?.kind === "run"
        ? (selected.detail?.playbook ?? selected.run.playbook)
        : null;
  const playbook = useRunsStore((s) =>
    playbookName === null ? undefined : s.playbookDetails[playbookName],
  );
  const playbookError = useRunsStore((s) =>
    playbookName === null ? undefined : s.playbookDetailErrors[playbookName],
  );
  const isStartingThisDraft = startingDraftId === runId;

  // Another run's block settings do not belong next to this one.
  useEffect(() => {
    closeRunNodeConfigDrawer();
  }, [runId, closeRunNodeConfigDrawer]);

  // Not on the loaded page: the backend is asked once.
  useEffect(() => {
    if (kind === "loading") {
      void lookUpRun(runId);
    }
  }, [kind, runId, lookUpRun]);

  // A run that is not there, or a draft that is gone: back to the overview. Not while the draft
  // is being started, as it leaves the drafts just before its run shows.
  useEffect(() => {
    if (kind === "missing" && !isStartingThisDraft) {
      navigate(projectRunHref(projectId), { replace: true });
    }
  }, [kind, isStartingThisDraft, navigate, projectId]);

  useEffect(() => {
    if (playbookName !== null) {
      void loadPlaybookDetail(playbookName);
    }
  }, [playbookName, loadPlaybookDetail]);

  const hasExpanded = expanded !== undefined;

  useEffect(() => {
    if (kind === "run" && !hasExpanded) {
      void refreshRunDetails(runId);
    }
  }, [kind, hasExpanded, runId, refreshRunDetails]);

  // Messages stay visible for a limited time, then hide.
  useEffect(() => {
    if (startError === null) {
      return;
    }

    const timer = setTimeout(clearStartError, messageVisibilityMs);

    return () => clearTimeout(timer);
  }, [startError, clearStartError]);

  if (selected === null || selected.kind === "loading" || selected.kind === "missing") {
    return (
      <Notice>
        <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
        {isStartingThisDraft ? "Starting the run..." : "Loading run..."}
      </Notice>
    );
  }

  if (selected.kind === "error") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="text-[12px] text-red-300" role="alert">
          {selected.message}
        </p>
        <BackLink projectId={projectId} />
      </div>
    );
  }

  const draft: RunDraft | null = selected.kind === "draft" ? selected.draft : null;
  const runConfig =
    selected.kind === "run" && selected.detail !== null && isObject(selected.detail.config)
      ? selected.detail.config
      : null;
  const steps =
    playbook === undefined
      ? []
      : draft !== null
        ? getActiveSteps(playbook, draft.config)
        : getRunSteps(playbook, runConfig);
  const runStatus =
    selected.kind === "run"
      ? normalizeRunStatus(
          expanded?.logs?.run_status || selected.detail?.status || selected.run.status,
        )
      : null;
  const nodeStatus: RunFlowNodeStatus = runStatus === null ? "planned" : toNodeStatus(runStatus);

  const stepErrors =
    draft !== null && playbook !== undefined ? getStepErrors(playbook, draft.config) : null;
  const blockedReason =
    draft === null
      ? null
      : playbook === undefined
        ? "The playbook is still loading."
        : describeStepErrors(stepErrors ?? new Map());
  const isStartDisabled = startingDraftId !== null || blockedReason !== null;

  async function handleStart() {
    if (draft === null) {
      return;
    }

    const uuid = await startDraft(draft.id);

    if (uuid !== null) {
      navigate(projectRunHref(projectId, uuid));
    }
  }

  return (
    <div className="bg-surface-900 relative flex h-full w-full flex-col overflow-hidden">
      <div className="border-surface-600 flex h-10 shrink-0 items-center gap-3 border-b px-3">
        <BackLink projectId={projectId} />
        <span className="text-surface-600" aria-hidden="true">
          /
        </span>
        <h1 className="text-surface-50 min-w-0 truncate text-[13px] font-semibold">
          {draft?.playbook ?? (selected.kind === "run" ? selected.run.name : "")}
        </h1>
      </div>

      <div className="border-surface-600 shrink-0 border-b p-3">
        {draft !== null ? (
          <div className="border-surface-600 bg-surface-800/50 text-surface-400 flex items-center gap-2 rounded-lg border border-dashed p-3 text-[12px]">
            <LuCircleDashed className="text-surface-500 shrink-0" size={16} aria-hidden="true" />
            Not started yet — review the Planned Flow, then Start.
          </div>
        ) : selected.kind === "run" ? (
          <dl className="border-surface-700 bg-surface-800 grid grid-cols-2 gap-3 rounded-lg border p-3 lg:grid-cols-4">
            <div>
              <dt className={cardLabelClassName}>Status</dt>
              <dd className="mt-1">
                {runStatus === null ? null : <RunStatusBadge status={runStatus} />}
              </dd>
            </div>
            <div>
              <dt className={cardLabelClassName}>Started</dt>
              <dd className="text-surface-50 mt-1 text-[13px] font-semibold">
                {formatRunStartedAt(selected.detail?.created_at ?? selected.run.startedAt)}
              </dd>
            </div>
            <div className="min-w-0">
              <dt className={cardLabelClassName}>Run UUID</dt>
              <dd
                className="text-surface-50 mt-1 truncate font-mono text-[12px]"
                title={selected.run.id}
              >
                {selected.run.id}
              </dd>
            </div>
            <div className="min-w-0">
              <dt className={cardLabelClassName}>Playbook</dt>
              <dd className="text-surface-50 mt-1 truncate text-[13px] font-semibold">
                {selected.run.playbook}
              </dd>
            </div>
          </dl>
        ) : null}
      </div>

      <div className="border-surface-600 shrink-0 border-b p-3">
        <div className="border-surface-700 bg-surface-800 rounded-lg border p-3">
          <h2 className={`${cardLabelClassName} mb-2`}>Input</h2>
          <dl className="flex flex-col gap-1 text-[12px]">
            {draft !== null ? (
              <>
                <InputRow label="Scenario" value={draft.scenarioLabel ?? "None (base model)"} />
                <InputRow label="Playbook" value={draft.playbook} />
                <InputRow label="Data record" value={draft.dataRecord.name} />
              </>
            ) : selected.kind === "run" ? (
              <>
                {/* The backend does not keep the scenario of a run. */}
                <InputRow label="Scenario" value="Not recorded for started runs" />
                <InputRow label="Playbook" value={selected.run.playbook} />
              </>
            ) : null}
          </dl>
        </div>
      </div>

      {playbookError !== undefined ? (
        <div
          className="shrink-0 border-b border-red-500/40 bg-red-500/10 p-3 text-[12px] text-red-300"
          role="alert"
        >
          {playbookError}
        </div>
      ) : playbook === undefined ? (
        <div className="text-surface-400 border-surface-600 flex h-64 shrink-0 items-center justify-center gap-2 border-b text-[12px]">
          <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
          Loading playbook...
        </div>
      ) : (
        <RunFlowSnapshot
          onSelectStep={openRunNodeConfigDrawer}
          selectedStepName={configuringRunNodeId}
          status={nodeStatus}
          steps={steps}
        />
      )}

      <div className="bg-surface-950 min-h-0 flex-1 overflow-y-auto p-3 pb-24 font-mono text-[11px]">
        {draft !== null ? (
          <div className="text-surface-500">No log yet — this run hasn&apos;t started.</div>
        ) : expanded === undefined || (expanded.isLoading && expanded.logs === null) ? (
          <div className="text-surface-400 flex items-center gap-2">
            <FiRefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
            Loading run details...
          </div>
        ) : expanded.error !== null && expanded.logs === null ? (
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12px] text-red-300" role="alert">
              {expanded.error}
            </span>
            <button
              className="border-surface-600 text-surface-200 hover:bg-surface-700 rounded border px-2 py-1 text-[12px] font-medium outline-none"
              onClick={() => void refreshRunDetails(runId)}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : (
          <>
            {expanded.error !== null ? (
              <p className="mb-2 text-[12px] text-red-300" role="alert">
                {expanded.error}
              </p>
            ) : null}
            <RunLogsSection
              autoRefreshMs={logsRefreshMs}
              logClassName="bg-transparent p-0"
              onRefresh={() => void refreshRunDetails(runId)}
              state={expanded}
              status={runStatus ?? undefined}
            />
          </>
        )}
        {draft !== null && startError !== null ? (
          <div className="mt-3 grid gap-2 text-[12px] text-red-300" role="alert">
            <p>{startError}</p>
            {startIssues.length > 0 ? (
              <ul className="list-disc pl-5">
                {startIssues.map((issue, index) => (
                  <li key={`${issue.kind}:${index}`}>
                    <span className="font-semibold">
                      {[...issue.step_path, ...(issue.config_path ?? [])].join(" › ") || "playbook"}
                    </span>
                    : {issue.message.charAt(0).toUpperCase() + issue.message.slice(1)}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {draft !== null && blockedReason !== null && startError === null ? (
          <p className="mt-3 text-[12px] text-red-300" role="alert">
            {blockedReason}
          </p>
        ) : null}
      </div>

      {draft !== null ? (
        <button
          aria-label="Start run"
          className="bg-accent-600 shadow-accent-600/40 hover:bg-accent-500 focus-visible:ring-accent-300 absolute bottom-5 left-1/2 flex h-14 w-14 -translate-x-1/2 items-center justify-center rounded-full text-white shadow-xl transition-transform outline-none hover:scale-105 focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50"
          disabled={isStartDisabled}
          onClick={() => void handleStart()}
          title={
            blockedReason ??
            (startPhase === "validating"
              ? "Checking the settings..."
              : startPhase === "submitting"
                ? "Starting the run..."
                : "Start run")
          }
          type="button"
        >
          {startPhase === null ? (
            <LuCirclePlay size={26} aria-hidden="true" />
          ) : (
            <FiRefreshCw className="size-6 animate-spin" aria-hidden="true" />
          )}
        </button>
      ) : null}
    </div>
  );
}
