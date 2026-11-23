// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useEffect } from "react";
import { isGroupLevel } from "../level";
import { useLevelPage } from "../level-page-context";
import { useLevelStore } from "../level-store";
import { RESULT_ATTRIBUTES } from "./attributes";
import { AttributesView } from "./attributes-view";
import { StatisticsView } from "./statistics-view";

// The chart drawer under the split: Statistics (the level's standard charts)
// or Attributes (one series attribute of its members, or the series picked
// in the table). Statistics by default on All entities and All locations,
// Attributes elsewhere; a single entity has no statistics.

export function LevelChartDrawer() {
  const { level, stage, result } = useLevelPage();
  const chartMode = useLevelStore((s) => s.chartMode);
  const picked = useLevelStore((s) => s.pickedSeries);
  const setPicked = useLevelStore((s) => s.setPickedSeries);
  // Results are read from a run result, shown on Inspect.
  const inspect = stage === "inspect" && result !== null;

  // Build has no results: result series picked on Inspect go.
  const hasResultPicks =
    !inspect && picked.some((series) => RESULT_ATTRIBUTES.has(series.attribute));
  useEffect(() => {
    if (hasResultPicks)
      setPicked(
        useLevelStore
          .getState()
          .pickedSeries.filter((series) => !RESULT_ATTRIBUTES.has(series.attribute)),
      );
  }, [hasResultPicks, setPicked]);

  const defaultMode =
    level.kind === "all-entities" || level.kind === "all-locations" ? "statistics" : "attributes";
  const mode =
    !isGroupLevel(level) || picked.length > 0 ? "attributes" : (chartMode ?? defaultMode);
  return mode === "statistics" ? (
    <StatisticsView inspect={inspect} />
  ) : (
    <AttributesView inspect={inspect} />
  );
}
