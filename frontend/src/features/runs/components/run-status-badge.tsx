import { statusMeta } from "../status";
import type { RunStatus } from "../types";

type RunStatusBadgeProps = {
  status: RunStatus;
};

export function RunStatusBadge({ status }: RunStatusBadgeProps) {
  const meta = statusMeta[status];
  const StatusIcon = meta.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${meta.badgeClassName}`}
    >
      <StatusIcon className={`size-3.5 ${meta.iconClassName ?? ""}`} aria-hidden="true" />
      {meta.label}
    </span>
  );
}
