import type { IconType } from "react-icons";
import { FiActivity, FiCheckCircle, FiClock, FiRefreshCw, FiXCircle } from "react-icons/fi";
import type { RunStatus } from "./types";

// Manta starts every run at once, never at a set time. A run Prefect holds as SCHEDULED is
// therefore waiting: at most so many playbook runs execute at once, and it starts when a slot
// frees up. "Scheduled" would say the wrong thing, so it is shown as queued.
const queuedStatus = "SCHEDULED";
// Not a Prefect state: the backend reports it for a failed run that exceeded its timeout, so
// that it can be told from a run that failed for another reason.
const timedOutStatus = "TIMED_OUT";

// The Prefect states, and the one status the backend adds to them.
export const runStatusOptions = [
  "SCHEDULED",
  "PENDING",
  "RUNNING",
  "COMPLETED",
  "FAILED",
  timedOutStatus,
  "CRASHED",
  "CANCELLING",
  "CANCELLED",
  "PAUSED",
] satisfies RunStatus[];

export const statusOptions = runStatusOptions.map((status) => ({
  label: formatRunStatus(status),
  value: status,
}));

export function normalizeRunStatus(status: string): RunStatus {
  return status.trim().toUpperCase() || "UNKNOWN";
}

/** A finished run: its status will not change again, so there is nothing left to poll. */
export function isRunFinished(status: string) {
  return ["COMPLETED", "FAILED", timedOutStatus, "CRASHED", "CANCELLED"].includes(
    normalizeRunStatus(status),
  );
}

/** Whether any of the runs can still change status, so the list is worth asking for again. */
export function hasUnfinishedRun(runs: { status: string }[]) {
  return runs.some((run) => !isRunFinished(run.status));
}

export function formatRunStatus(status: string) {
  const normalized = normalizeRunStatus(status);

  if (normalized === queuedStatus) {
    return "Queued";
  }

  return normalized
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

const statusHints: Record<string, string> = {
  [queuedStatus]: "Waiting for a free slot. The run starts once another run finishes.",
  [timedOutStatus]: "The run took longer than allowed and was stopped.",
};

/** What a status means, for the ones that are not clear from their name; null for the others. */
export function getRunStatusHint(status: string): string | null {
  return statusHints[normalizeRunStatus(status)] ?? null;
}

export function getStatusBadgeMeta(status: RunStatus): {
  badgeClassName: string;
  icon: IconType;
  iconClassName?: string;
} {
  switch (normalizeRunStatus(status)) {
    case "COMPLETED":
      return { badgeClassName: "bg-ok-500/10 text-ok-500", icon: FiCheckCircle };
    case "FAILED":
    case "CRASHED":
      return { badgeClassName: "bg-danger-500/10 text-danger-500", icon: FiXCircle };
    case timedOutStatus:
      return { badgeClassName: "bg-danger-500/10 text-danger-500", icon: FiClock };
    case "RUNNING":
      return {
        badgeClassName: "bg-accent-500/10 text-accent-400",
        icon: FiRefreshCw,
        iconClassName: "animate-spin",
      };
    case "SCHEDULED":
    case "PENDING":
      return { badgeClassName: "bg-surface-700 text-surface-300", icon: FiClock };
    default:
      return { badgeClassName: "bg-surface-700 text-surface-300", icon: FiActivity };
  }
}
