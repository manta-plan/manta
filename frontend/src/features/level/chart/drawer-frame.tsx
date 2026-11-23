// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { Segmented } from "../../../components/segmented";
import { FullscreenButton } from "../fullscreen/fullscreen-button";
import type { ReactNode } from "react";
import { LuChartLine, LuMousePointerClick } from "react-icons/lu";
import { useShownData } from "../../project/lib/record-data";
import { useLevelPage } from "../level-page-context";
import { scopeKey } from "../level-sql";
import { useLevelStore, type ChartDrawerMode } from "../level-store";
import { loadAxis } from "./chart-sql";

// The chart drawer's frame: "Chart", the Statistics | Attributes switch, the
// mode's selectors, the period and window it reads, its actions and the
// full screen button, then the chart and a hint.

const STATISTICS_OFF =
  "Statistics are available for groups of entities. Go up a level to see them.";

export function DrawerFrame({
  mode,
  statisticsOn,
  controls,
  actions,
  children,
}: {
  mode: ChartDrawerMode;
  statisticsOn: boolean;
  controls: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col pb-2">
      <div className="border-surface-700 bg-surface-800 flex min-h-11 flex-wrap items-center gap-2 border-b px-3 py-1.5">
        <span className="text-surface-100 flex items-center gap-1.5 text-[12px] font-medium">
          <LuChartLine size={13} className="text-surface-400" />
          Chart
        </span>
        <ModeSwitch mode={mode} statisticsOn={statisticsOn} />
        {controls}
        <span className="flex-1" />
        <PeriodNote />
        {actions}
        <FullscreenButton block="chart" />
      </div>
      {children}
      <div className="text-surface-500 flex items-center gap-1.5 px-3 pt-1 text-[11px]">
        <LuMousePointerClick size={12} className="shrink-0" />
        Or click time series cells in the table to pick individual series of one attribute.
      </div>
    </div>
  );
}

function ModeSwitch({ mode, statisticsOn }: { mode: ChartDrawerMode; statisticsOn: boolean }) {
  const setMode = useLevelStore((s) => s.setChartMode);
  const { level } = useLevelPage();
  const statisticsTitle = !statisticsOn
    ? STATISTICS_OFF
    : level.kind === "all-entities"
      ? "Standard charts for the whole scenario"
      : "Standard charts for the entities in the table above";
  return (
    <Segmented
      ariaLabel="Chart type"
      value={mode}
      onChange={setMode}
      options={[
        {
          value: "statistics",
          label: "Statistics",
          title: statisticsTitle,
          disabled: !statisticsOn,
        },
        {
          value: "attributes",
          label: "Attributes",
          title: "Time-varying attributes of the entities in the table above",
        },
      ]}
    />
  );
}

/** "Period 2030 · Winter, hourly": what every chart reads. */
function PeriodNote() {
  const { scope } = useLevelPage();
  const timeWindow = useLevelStore((s) => s.timeWindow);
  const axis = useShownData(
    "level-chart-axis",
    scope ? [scopeKey({ ...scope, level: { kind: "all-entities" }, locations: [] })] : null,
    () => loadAxis(scope!),
  );
  if (!scope) return null;
  const hourly = axis.status === "ready" && axis.data.weights.every((weight) => weight === 1);
  const resolution =
    axis.status !== "ready"
      ? ""
      : hourly
        ? ", hourly"
        : `, ${axis.data.times.length.toLocaleString()} snapshots`;
  return (
    <span className="text-surface-400 text-[11px]">
      Period {scope.period} · {timeWindow?.label ?? "Full span"}
      {resolution}
    </span>
  );
}
