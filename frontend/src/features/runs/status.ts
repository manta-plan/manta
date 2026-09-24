import type { IconType } from "react-icons";
import {
  FiAlertTriangle,
  FiCheckCircle,
  FiClock,
  FiLoader,
  FiPauseCircle,
  FiRefreshCw,
  FiSlash,
  FiXCircle,
} from "react-icons/fi";
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

type StatusBadgeMeta = {
  badgeClassName: string;
  icon: IconType;
  iconClassName?: string;
};

const statusBadgeMetaByStatus: Record<(typeof prefectStateOptions)[number], StatusBadgeMeta> = {
  SCHEDULED: { badgeClassName: "bg-blue-50 text-blue-700", icon: FiClock },
  PENDING: { badgeClassName: "bg-amber-50 text-amber-700", icon: FiLoader },
  RUNNING: {
    badgeClassName: "bg-secondary/10 text-secondary",
    icon: FiRefreshCw,
    iconClassName: "animate-spin",
  },
  COMPLETED: { badgeClassName: "bg-emerald-50 text-emerald-700", icon: FiCheckCircle },
  FAILED: { badgeClassName: "bg-red-50 text-red-700", icon: FiXCircle },
  CRASHED: { badgeClassName: "bg-orange-50 text-orange-700", icon: FiAlertTriangle },
  CANCELLING: {
    badgeClassName: "bg-cyan-50 text-cyan-700",
    icon: FiSlash,
    iconClassName: "animate-pulse",
  },
  CANCELLED: { badgeClassName: "bg-surface-alt text-text-secondary", icon: FiSlash },
  PAUSED: { badgeClassName: "bg-violet-50 text-violet-700", icon: FiPauseCircle },
};

const unknownStatusBadgeMeta: StatusBadgeMeta = {
  badgeClassName: "bg-surface-alt text-text-secondary",
  icon: FiClock,
};

export function getStatusBadgeMeta(status: RunStatus): StatusBadgeMeta {
  const normalizedStatus = normalizeRunStatus(status) as (typeof prefectStateOptions)[number];
  return statusBadgeMetaByStatus[normalizedStatus] ?? unknownStatusBadgeMeta;
}
