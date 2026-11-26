import { useEffect, useMemo } from "react";
import { useShownData } from "../project/lib/record-data";
import { serverName, serverQuery } from "../project/lib/record-server/client";
import type { Level } from "./level";
import type { LevelQueryScope } from "./level-sql";
import { useLevelStore } from "./level-store";

// The record's investment periods (dimensions.snapshot's periods), each with its
// span of timesteps, and the one shown: global, first by default.

export interface PeriodSpan {
  period: string;
  /** First and last timestep, ISO (UTC). */
  start: string;
  end: string;
  /** Snapshots in the period. */
  snapshots: number;
}

function loadPeriods(): Promise<PeriodSpan[]> {
  return serverQuery<PeriodSpan>(`
    SELECT snapshot.period::VARCHAR AS period,
           strftime(min(snapshot.timestep), '%Y-%m-%dT%H:%M:00Z') AS start,
           strftime(max(snapshot.timestep), '%Y-%m-%dT%H:%M:00Z') AS "end",
           count(*)::INTEGER AS snapshots
    FROM ${serverName("dimensions.snapshot")}
    GROUP BY ALL ORDER BY min(snapshot.period)`);
}

/** The periods, and the one shown (kept valid: the first when the shown one isn't the record's). */
export function usePeriods(): {
  periods: PeriodSpan[];
  period: string | null;
  span: PeriodSpan | null;
  isLoading: boolean;
  error: string | null;
} {
  const data = useShownData("level-periods", [], loadPeriods);
  const ready = data.status === "ready" ? data.data : null;
  const periods = useMemo(() => ready ?? [], [ready]);
  const period = useLevelStore((s) => s.period);
  const setPeriod = useLevelStore((s) => s.setPeriod);
  const valid = periods.some((item) => item.period === period);
  useEffect(() => {
    if (!valid && periods.length > 0) setPeriod(periods[0].period);
  }, [periods, setPeriod, valid]);
  const shown = valid ? period : (periods[0]?.period ?? null);
  return {
    periods,
    period: shown,
    span: periods.find((item) => item.period === shown) ?? null,
    isLoading: data.status === "loading",
    error: data.status === "error" ? data.error : null,
  };
}

/** What a level's queries read: the level, the period and window, the map's location selection. Null until the periods are read. */
export function useLevelScope(level: Level): LevelQueryScope | null {
  const { period } = usePeriods();
  const timeWindow = useLevelStore((s) => s.timeWindow);
  const locations = useLevelStore((s) => s.selectedLocations);
  if (period === null) return null;
  return { level, period, timeWindow, locations };
}
