// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useMemo } from "react";
import { useShownData } from "../../project/lib/record-data";
import { useProjectStore } from "../../project/store/project-store";
import { isGroupLevel, isLocationLevel } from "../level";
import { useLevelPage } from "../level-page-context";
import { scopeKey } from "../level-sql";
import { useLevelStore } from "../level-store";
import {
  aggregationCaption,
  aggregationLabel,
  aggregationsFor,
  attributeOptions,
  loadAttributeChart,
  optionId,
  type Aggregation,
} from "./attributes";
import { loadAttributeOptions } from "./chart-sql";
import { Caption, ChartEmpty, ChartLoading, ChartSelect, CsvButton } from "./controls";
import { DrawerFrame } from "./drawer-frame";
import { PickedView } from "./picked-view";
import { SpecChart } from "./spec-chart";
import { sumUnit } from "./spec";

// Attributes mode: one series attribute of the level's members, summed,
// averaged, every series, or the largest; or, once series are picked in the
// table, those ("Picked in the table (n)"). Choosing another attribute or
// aggregation clears the picks (the store does).

const PLOT_HEIGHT = 240;
const PICKED = "picked";

export function AttributesView({ inspect }: { inspect: boolean }) {
  const { level, scope } = useLevelPage();
  const record = useProjectStore((s) => s.record);
  const picked = useLevelStore((s) => s.pickedSeries);
  const chosenAttribute = useLevelStore((s) => s.chartAttribute);
  const chosenAggregation = useLevelStore((s) => s.chartAggregation);
  const setAttribute = useLevelStore((s) => s.setChartAttribute);
  const setAggregation = useLevelStore((s) => s.setChartAggregation);
  const withBuses = isLocationLevel(level);
  const manifest = record?.info.manifest;

  const optionsData = useShownData(
    "level-chart-attributes",
    scope ? [scopeKey(scope), withBuses] : null,
    () => loadAttributeOptions(scope!, withBuses),
  );
  const options = useMemo(
    () =>
      optionsData.status === "ready"
        ? attributeOptions(
            optionsData.data.options,
            optionsData.data.ctypes,
            withBuses,
            manifest,
            inspect,
          )
        : [],
    [optionsData, withBuses, manifest, inspect],
  );

  const pickedId = picked.length > 0 ? optionId(picked[0].ctype, picked[0].attribute) : null;
  const option =
    options.find((item) => item.id === (pickedId ?? chosenAttribute)) ??
    options.find((item) => item.available) ??
    null;
  const aggregations = option ? aggregationsFor(option.unit) : [];
  const aggregation: Aggregation | null = aggregations.includes(chosenAggregation as Aggregation)
    ? (chosenAggregation as Aggregation)
    : (aggregations[0] ?? null);
  const isPicked = picked.length > 0;

  const ready = scope && option && option.available && option.n > 0 && aggregation && !isPicked;
  const chart = useShownData(
    "level-chart-attribute",
    ready ? [scopeKey(scope), option.id, aggregation, inspect] : null,
    () => loadAttributeChart(scope!, option!, aggregation!, inspect),
  );
  const spec = chart.status === "ready" ? chart.data : null;

  const attributeItems = options.map((item) => ({
    value: item.id,
    label: item.id,
    group: item.result ? "Run results" : "Inputs",
    disabled: !item.available,
    hint: "Available in Inspect",
  }));
  // A picked series of an attribute the level doesn't list (picked elsewhere) still shows as chosen.
  if (pickedId && !options.some((item) => item.id === pickedId))
    attributeItems.unshift({
      value: pickedId,
      label: pickedId,
      group: "Inputs",
      disabled: false,
      hint: "",
    });
  const aggregationItems = [
    ...aggregations.map((item) => ({
      value: item,
      label: aggregationLabel(item, option?.unit ?? null),
    })),
    ...(isPicked ? [{ value: PICKED, label: `Picked in the table (${picked.length})` }] : []),
  ];

  const controls = (pickedId || option) && (
    <>
      <ChartSelect
        ariaLabel="Attribute"
        value={pickedId ?? option?.id ?? null}
        items={attributeItems}
        onChange={(value) => value !== pickedId && setAttribute(value)}
      />
      {aggregationItems.length > 0 && (
        <ChartSelect
          ariaLabel="Aggregation"
          value={isPicked ? PICKED : aggregation}
          items={aggregationItems}
          onChange={(value) => value !== PICKED && setAggregation(value)}
        />
      )}
    </>
  );

  if (isPicked)
    return <PickedView inspect={inspect} controls={controls} statisticsOn={isGroupLevel(level)} />;

  let body;
  if (optionsData.status === "error")
    body = <ChartEmpty title="The attributes couldn't be read" detail={optionsData.error} />;
  else if (optionsData.status === "loading" || !scope) body = <ChartLoading height={PLOT_HEIGHT} />;
  else if (!option)
    body = (
      <ChartEmpty
        title="No time series here"
        detail={
          inspect
            ? "None of these entities has a time-varying attribute."
            : "None of these entities has a time-varying input. Switch to Inspect for results."
        }
      />
    );
  else if (!option.available)
    body = (
      <ChartEmpty
        title={`${option.id} is a result`}
        detail="Switch to Inspect to see it, or pick an input attribute."
      />
    );
  else if (option.n === 0)
    body = (
      <ChartEmpty title="Nothing to plot" detail="No entity in this group stores this attribute." />
    );
  else if (chart.status === "error")
    body = <ChartEmpty title="The chart couldn't be read" detail={chart.error} />;
  else if (chart.status === "loading") body = <ChartLoading height={PLOT_HEIGHT} />;
  else if (!spec)
    body = <ChartEmpty title="Nothing to plot" detail="No values in this time window." />;
  else {
    const unit = aggregation === "sum" ? sumUnit(option.unit).unit : (option.unit ?? "");
    body = (
      <div className={chart.refreshing ? "opacity-60 transition-opacity" : ""}>
        <Caption>
          <span className="text-surface-200">{option.id}</span> [{unit}] ·{" "}
          {aggregationCaption(option, aggregation!)}
        </Caption>
        <SpecChart spec={spec} height={PLOT_HEIGHT} />
      </div>
    );
  }

  return (
    <DrawerFrame
      mode="attributes"
      statisticsOn={isGroupLevel(level)}
      controls={controls}
      actions={spec && option && <CsvButton spec={spec} name={option.id.replace(" · ", "-")} />}
    >
      {body}
    </DrawerFrame>
  );
}
