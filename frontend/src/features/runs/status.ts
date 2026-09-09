import type { IconType } from "react-icons";
import { FiAlertCircle, FiCheckCircle, FiClock, FiRefreshCw } from "react-icons/fi";
import type { RunStatus } from "./types";

export const statusMeta = {
  Running: {
    label: "Running",
    badgeClassName: "bg-secondary/10 text-secondary",
    icon: FiRefreshCw,
    iconClassName: "animate-spin",
  },
  Completed: {
    label: "Completed",
    badgeClassName: "bg-accent/20 text-primary",
    icon: FiCheckCircle,
    iconClassName: undefined,
  },
  Failed: {
    label: "Failed",
    badgeClassName: "bg-red-50 text-red-700",
    icon: FiAlertCircle,
    iconClassName: undefined,
  },
  Queued: {
    label: "Queued",
    badgeClassName: "bg-surface-alt text-text-secondary",
    icon: FiClock,
    iconClassName: undefined,
  },
  Unknown: {
    label: "Unknown",
    badgeClassName: "bg-surface-alt text-text-secondary",
    icon: FiAlertCircle,
    iconClassName: undefined,
  },
} satisfies Record<
  RunStatus,
  { label: string; badgeClassName: string; icon: IconType; iconClassName?: string }
>;

export const statusOptions = Object.entries(statusMeta).map(([value, status]) => ({
  label: status.label,
  value: value as RunStatus,
}));

const backendStatusesByRunStatus = {
  Running: ["RUNNING"],
  Completed: ["COMPLETED"],
  Failed: ["FAILED", "CRASHED", "CANCELLED"],
  Queued: ["SCHEDULED", "PENDING", "PAUSED"],
  Unknown: ["UNKNOWN"],
} satisfies Record<RunStatus, string[]>;

export function getBackendStatusFilters(statuses: RunStatus[]) {
  return statuses.flatMap((status) => backendStatusesByRunStatus[status]);
}

export function normalizeRunStatus(status: string): RunStatus {
  switch (status.toUpperCase()) {
    case "RUNNING":
      return "Running";
    case "COMPLETED":
      return "Completed";
    case "FAILED":
    case "CRASHED":
    case "CANCELLED":
      return "Failed";
    case "SCHEDULED":
    case "PENDING":
    case "PAUSED":
      return "Queued";
    default:
      return "Unknown";
  }
}
