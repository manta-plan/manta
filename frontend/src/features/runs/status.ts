import type { IconType } from "react-icons";
import { FiActivity, FiRefreshCw } from "react-icons/fi";
import type { RunStatus } from "./types";

export const prefectStateOptions = [
  "SCHEDULED",
  "PENDING",
  "RUNNING",
  "COMPLETED",
  "FAILED",
  "CRASHED",
  "CANCELLING",
  "CANCELLED",
  "PAUSED",
] satisfies RunStatus[];

export const statusOptions = prefectStateOptions.map((status) => ({
  label: formatRunStatus(status),
  value: status,
}));

export function normalizeRunStatus(status: string): RunStatus {
  return status.trim().toUpperCase() || "UNKNOWN";
}

export function formatRunStatus(status: string) {
  return normalizeRunStatus(status)
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function getStatusBadgeMeta(status: RunStatus): {
  badgeClassName: string;
  icon: IconType;
  iconClassName?: string;
} {
  return {
    badgeClassName:
      normalizeRunStatus(status) === "RUNNING"
        ? "bg-secondary/10 text-secondary"
        : "bg-surface-alt text-text-secondary",
    icon: normalizeRunStatus(status) === "RUNNING" ? FiRefreshCw : FiActivity,
    iconClassName: normalizeRunStatus(status) === "RUNNING" ? "animate-spin" : undefined,
  };
}
