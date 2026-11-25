// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useMemo } from "react";
import { useShownData } from "../../project/lib/record-data";
import { useProjectStore } from "../../project/store/project-store";
import { useLevelPage } from "../level-page-context";
import { scopeKey } from "../level-sql";
import { useLevelStore } from "../level-store";
import { Caption, ChartEmpty, ChartLoading, ChartSelect, CsvButton } from "./controls";
import { DrawerFrame } from "./drawer-frame";
import { SpecChart } from "./spec-chart";
import { NEUTRAL } from "./spec";
import { statisticsFor, type StatisticContext } from "./statistics";

// Statistics mode: the level's standard charts. The one chosen is kept by
// base name; a level without it shows its first one. A result statistic in
// Build is greyed ("Available in Inspect").

const PLOT_HEIGHT = 240;

export function StatisticsView({ inspect }: { inspect: boolean }) {
  const { level, scope } = useLevelPage();
  const chosen = useLevelStore((s) => s.chartStatistic);
  const setChosen = useLevelStore((s) => s.setChartStatistic);
  const record = useProjectStore((s) => s.record);
  const statistics = useMemo(() => statisticsFor(level, inspect), [level, inspect]);
  const statistic =
    statistics.find((item) => item.base === chosen) ??
    statistics.find((item) => !item.result || inspect) ??
    null;
  const blocked = statistic !== null && statistic.result && !inspect;

  const carriers = record?.carriers;
  const carrier = useCallback<StatisticContext["carrier"]>(
    (name) => {
      const known = name ? carriers?.[name] : undefined;
      return { name: known?.niceName || name || "(no carrier)", color: known?.color || NEUTRAL };
    },
    [carriers],
  );
  const priceUnit = record?.info.manifest.attributes.marginal_price?.unit ?? "€/MWh";
  const data = useShownData(
    "level-chart-statistic",
    scope && statistic && !blocked ? [scopeKey(scope), statistic.base, inspect] : null,
    () => statistic!.load({ scope: scope!, inspect, carrier, priceUnit }),
  );

  const items = statistics.map((item) => ({
    value: item.base,
    label: item.label,
    group: item.result ? "Run results" : "Inputs",
    disabled: item.result && !inspect,
    hint: "Available in Inspect",
  }));
  const spec = data.status === "ready" ? data.data : null;

  let body;
  if (statistics.length === 0)
    body = (
      <ChartEmpty
        title="No statistics here"
        detail="Switch to Attributes to chart a time series of the entities above."
      />
    );
  else if (!statistic)
    body = (
      <ChartEmpty
        title="No statistic selected"
        detail="Choose a statistic, or switch to Attributes."
      />
    );
  else if (blocked)
    body = (
      <ChartEmpty
        title={`${statistic.label} needs a run result`}
        detail="Available in Inspect. Pick an input statistic to see it here."
      />
    );
  else if (data.status === "error")
    body = <ChartEmpty title="The chart couldn't be read" detail={data.error} />;
  else if (data.status === "loading") body = <ChartLoading height={PLOT_HEIGHT} />;
  else if (!spec)
    body = (
      <ChartEmpty
        title="Nothing to plot"
        detail="No entity at this level has the values this statistic needs."
      />
    );
  else
    body = (
      <div className={data.refreshing ? "opacity-60 transition-opacity" : ""}>
        <Caption>{statistic.note}</Caption>
        <SpecChart spec={spec} height={PLOT_HEIGHT} />
      </div>
    );

  return (
    <DrawerFrame
      mode="statistics"
      statisticsOn
      controls={
        statistics.length > 0 && (
          <ChartSelect
            ariaLabel="Choose a statistic"
            placeholder="Choose a statistic…"
            value={statistic?.base ?? null}
            items={items}
            onChange={setChosen}
          />
        )
      }
      actions={spec && statistic && <CsvButton spec={spec} name={statistic.label} />}
    >
      {body}
    </DrawerFrame>
  );
}
