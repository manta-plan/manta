import { useEffect } from "react";
import { hasUnfinishedRun } from "./status";
import { useRunsStore } from "./store/runs-store";

// The listed runs refresh at this interval while one of them is not finished.
const runsRefreshMs = 10_000;

/**
 * Keeps the statuses of the listed runs up to date without a manual Refresh: a queued run
 * shows as running once it gets a slot, and a running one as finished. Stops once every
 * listed run is finished, as none of them can change again.
 */
export function useRunsAutoRefresh() {
  const shouldPoll = useRunsStore((s) => hasUnfinishedRun(s.runs));
  const refresh = useRunsStore((s) => s.refresh);

  useEffect(() => {
    if (!shouldPoll) return;
    const timer = setInterval(() => {
      // Skip a tick while a load is still in flight, so it is not replaced by this one.
      if (!useRunsStore.getState().isRefreshingRuns) void refresh();
    }, runsRefreshMs);
    return () => clearInterval(timer);
  }, [shouldPoll, refresh]);
}
