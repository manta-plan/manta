// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { IconType } from "react-icons";
import { FiActivity, FiCheckCircle, FiClock, FiRefreshCw, FiXCircle } from "react-icons/fi";
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
  switch (normalizeRunStatus(status)) {
    case "COMPLETED":
      return { badgeClassName: "bg-ok-500/10 text-ok-500", icon: FiCheckCircle };
    case "FAILED":
    case "CRASHED":
      return { badgeClassName: "bg-danger-500/10 text-danger-500", icon: FiXCircle };
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
