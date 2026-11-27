// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useChartHeight } from "./use-chart-height";
import type { ReactNode } from "react";
import { Select } from "@base-ui/react/select";
import { LuChartLine, LuCheck, LuChevronDown, LuDownload } from "react-icons/lu";
import { SkeletonBlock } from "../../../components/widget-states";
import { downloadCsv, type ChartSpec } from "./spec";

// The chart drawer's small parts: a compact dropdown whose greyed items say
// why, an icon button, an empty state and a loading block.

export interface ChartSelectItem {
  value: string;
  label: string;
  /** Listed, but can't be picked; `hint` says why. */
  disabled?: boolean;
  hint?: string;
  group?: string;
}

export function ChartSelect({
  value,
  items,
  onChange,
  ariaLabel,
  placeholder,
}: {
  value: string | null;
  items: ChartSelectItem[];
  onChange: (value: string) => void;
  ariaLabel: string;
  placeholder?: string;
}) {
  const groups = [...new Set(items.map((item) => item.group ?? ""))];
  const renderItem = (item: ChartSelectItem) => (
    <Select.Item
      key={item.value}
      value={item.value}
      disabled={item.disabled}
      title={item.disabled ? item.hint : undefined}
      className="text-surface-200 data-[disabled]:text-surface-500 data-[highlighted]:bg-surface-700 data-[selected]:text-surface-50 flex min-h-7 cursor-pointer items-center gap-2 rounded px-2 py-1 text-[12px] outline-none"
    >
      <Select.ItemText className="min-w-0 flex-1 truncate">{item.label}</Select.ItemText>
      {item.disabled && item.hint && (
        <span className="text-surface-500 shrink-0 text-[10px]">{item.hint}</span>
      )}
      <Select.ItemIndicator className="text-accent-400">
        <LuCheck size={12} />
      </Select.ItemIndicator>
    </Select.Item>
  );
  return (
    <Select.Root
      value={value}
      onValueChange={(next) => next !== null && onChange(next)}
      items={items.map((item) => ({ value: item.value, label: item.label }))}
    >
      <Select.Trigger
        aria-label={ariaLabel}
        className="border-surface-600 bg-surface-900 text-surface-50 hover:border-surface-500 focus-visible:border-accent-500 flex h-7 max-w-[22rem] min-w-0 items-center gap-1.5 rounded border px-2 text-left text-[12px] outline-none"
      >
        <Select.Value
          className="data-[placeholder]:text-surface-500 min-w-0 flex-1 truncate"
          placeholder={placeholder}
        />
        <Select.Icon className="text-surface-400">
          <LuChevronDown size={12} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner
          sideOffset={4}
          align="start"
          alignItemWithTrigger={false}
          className="z-50"
        >
          <Select.Popup className="border-surface-600 bg-surface-800 max-h-[min(24rem,var(--available-height))] min-w-[var(--anchor-width)] overflow-y-auto rounded border p-1 shadow-xl outline-none">
            <Select.List>
              {groups.map((group) =>
                group ? (
                  <Select.Group key={group}>
                    <Select.GroupLabel className="text-surface-500 px-2 pt-1.5 pb-0.5 text-[10px] font-medium tracking-wide uppercase">
                      {group}
                    </Select.GroupLabel>
                    {items.filter((item) => item.group === group).map(renderItem)}
                  </Select.Group>
                ) : (
                  items.filter((item) => !item.group).map(renderItem)
                ),
              )}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}

export function IconButton({
  label,
  onClick,
  pressed,
  children,
}: {
  label: string;
  onClick: () => void;
  pressed?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={`focus-visible:ring-accent-500 grid h-7 w-7 shrink-0 place-items-center rounded border outline-none focus-visible:ring-1 ${
        pressed
          ? "border-accent-600 bg-accent-700/30 text-surface-50"
          : "border-surface-600 text-surface-300 hover:bg-surface-700 hover:text-surface-100"
      }`}
    >
      {children}
    </button>
  );
}

export function ChartEmpty({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex min-h-[12rem] flex-col items-center justify-center gap-1 px-4 text-center">
      <LuChartLine size={16} className="text-surface-500" />
      <div className="text-surface-200 text-[12px] font-medium">{title}</div>
      {detail && <div className="text-surface-400 max-w-md text-[11px]">{detail}</div>}
    </div>
  );
}

export function ChartLoading({ height = 220 }: { height?: number }) {
  const shownHeight = useChartHeight(height);
  return (
    <div role="status" aria-label="Loading the chart" className="px-3 py-2">
      <SkeletonBlock className="w-full" style={{ height: shownHeight }} />
    </div>
  );
}

/** A chart's caption, above the plot. */
export function Caption({ children }: { children: ReactNode }) {
  return <div className="text-surface-400 truncate px-3 pt-2 text-[11px]">{children}</div>;
}

/** Downloads a time series chart wide: Time, then one column per series (a distribution: its quantiles). */
export function CsvButton({ spec, name }: { spec: ChartSpec; name: string }) {
  if (spec.kind !== "time") return null;
  const { distribution } = spec;
  const columns = distribution
    ? (["min", "p25", "median", "p75", "max"] as const).map((key) => ({
        header: `${key} [${spec.unit}]`,
        values: distribution[key],
      }))
    : spec.series.map((series) => ({
        header: `${series.name} [${spec.unit}]`,
        values: series.values,
      }));
  if (columns.length === 0) return null;
  return (
    <IconButton label="Download CSV" onClick={() => downloadCsv(name, spec.times, columns)}>
      <LuDownload size={13} />
    </IconButton>
  );
}
