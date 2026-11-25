// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { Drawer } from "@base-ui/react/drawer";
import { LuGitCompareArrows, LuX } from "react-icons/lu";
import { SidebarSkeletonBlock } from "../../../components/widget-states";
import {
  entityLabel,
  formatNumber,
  formatRatio,
  formatValue,
} from "../../project/lib/record-format";
import { useShownData } from "../../project/lib/record-data";
import { getScenarioChange } from "../../project/lib/record-server/queries";
import type { ScenarioChange } from "../../project/lib/record-server/types";
import { skeletonWidth } from "../../project/lib/skeleton";
import { useProjectStore } from "../../project/store/project-store";

const SNAP_POINTS = ["160px", 0.5, 0.92];

function Message({ children }: { children: string }) {
  return (
    <div className="text-surface-400 flex h-full items-center justify-center text-[12px]">
      {children}
    </div>
  );
}

// While the table loads: a header and rows of cells, in the table's own row height.
function TableSkeleton({ columns = 4 }: { columns?: number }) {
  const widths = Array.from({ length: columns }, (_, index) => skeletonWidth(index));
  return (
    <div role="status" aria-label="Loading" className="flex flex-col">
      <div className="border-surface-600 flex h-[29px] items-center gap-6 border-b px-3">
        {widths.map((_, index) => (
          <SidebarSkeletonBlock key={index} className="h-2.5 w-20 shrink-0" />
        ))}
      </div>
      {Array.from({ length: 12 }, (_, row) => (
        <div
          key={row}
          className="border-surface-700/60 flex h-[25px] items-center gap-6 border-b px-3"
        >
          {widths.map((_, index) => (
            <SidebarSkeletonBlock
              key={index}
              className="h-2.5 shrink-0"
              style={{ width: index === 0 ? 160 : 80 }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

// One attribute a scenario changes: per entity or bus, its value in the
// parent revision and in the scenario. A series shows how many of its rows
// changed instead, with their median ratio.
function ScenarioChangeTable({ scenario, attribute }: { scenario: string; attribute: string }) {
  const record = useProjectStore((s) => s.record);
  const state = useShownData<ScenarioChange[]>("scenario-change", [scenario, attribute], () =>
    getScenarioChange(scenario, attribute),
  );

  if (state.status === "error") return <Message>{state.error}</Message>;
  if (state.status === "loading" || !record) return <TableSkeleton />;
  const data = state.data;
  const revisions = record.info.revisions;
  const revision = revisions.find((r) => r.name === scenario);
  const parent = revisions.find((r) => r.name === revision?.parent);
  const spec = record.info.manifest.attributes[attribute];
  const isSeries = data.some((row) => row.seriesRows > 0);
  const isBus = data[0]?.dim === "bus";
  const show = (value: string | null) => formatValue(value, { dtype: spec?.dtype, unit: null });
  const cell = "border-b border-surface-700/60 px-3 py-1 whitespace-nowrap";
  const head = "border-b border-surface-600 px-3 py-1.5 font-medium whitespace-nowrap";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-surface-700 bg-surface-800 text-surface-400 flex min-h-10 shrink-0 items-center gap-2 border-b px-3 py-1.5 text-[11px]">
        <span title={spec?.description}>
          {data.length.toLocaleString()}{" "}
          {isBus
            ? data.length === 1
              ? "bus"
              : "buses"
            : data.length === 1
              ? "entity"
              : "entities"}
          {spec?.unit && ` · ${spec.unit}`} · before is {parent?.label ?? "the parent"}, after is{" "}
          {revision?.label ?? scenario}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <thead className="bg-surface-800 text-surface-400 sticky top-0 z-10 text-left">
            <tr>
              <th className={`bg-surface-800 sticky left-0 ${head}`}>{isBus ? "Bus" : "Entity"}</th>
              <th className={head}>Location</th>
              {!isBus && <th className={head}>Carrier</th>}
              {isSeries ? (
                <th className={head}>Changed rows</th>
              ) : (
                <>
                  <th className={head}>Before</th>
                  <th className={head}>After</th>
                </>
              )}
              <th className={head}>{isSeries ? "Median ratio" : "Ratio"}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => {
              const carrier = row.carrier ? record.carriers[row.carrier] : undefined;
              const name = row.bus ? `${row.label} → ${row.bus}` : row.label;
              return (
                <tr
                  key={`${row.label}\n${row.bus}`}
                  className="text-surface-200 hover:bg-surface-700/60"
                >
                  <td
                    className={`bg-surface-800 sticky left-0 max-w-[320px] truncate font-mono ${cell}`}
                    title={name}
                  >
                    {isBus ? row.label : entityLabel(row.label, row.location)}
                    {row.bus && <span className="text-surface-500"> → {row.bus}</span>}
                  </td>
                  <td className={`text-surface-400 ${cell}`}>{row.location ?? "—"}</td>
                  {!isBus && (
                    <td className={`text-surface-400 ${cell}`}>
                      <span className="flex items-center gap-1.5">
                        {carrier?.color && (
                          <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ backgroundColor: carrier.color }}
                          />
                        )}
                        {carrier?.niceName || row.carrier || "—"}
                      </span>
                    </td>
                  )}
                  {isSeries ? (
                    <td className={`text-surface-300 tabular-nums ${cell}`}>
                      {formatNumber(row.seriesRows)}
                    </td>
                  ) : (
                    <>
                      <td className={`text-surface-400 tabular-nums ${cell}`}>
                        {show(row.before)}
                      </td>
                      <td className={`text-surface-100 tabular-nums ${cell}`}>{show(row.after)}</td>
                    </>
                  )}
                  <td className={`text-accent-300 tabular-nums ${cell}`}>
                    {formatRatio(row.ratio)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// The drawer covers the main area only, not the sidebar: its left and right
// edges follow the main area (which the sidebar resizes).
function useMainBounds(): { left: number; right: number } | null {
  const [bounds, setBounds] = useState<{ left: number; right: number } | null>(null);

  useEffect(() => {
    const main = document.querySelector<HTMLElement>('[data-tour="run-main-section"]');
    if (!main) return;
    const measure = () => {
      const rect = main.getBoundingClientRect();
      setBounds({ left: rect.left, right: window.innerWidth - rect.right });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(main);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  return bounds;
}

// The bottom drawer a Scenarios panel change row opens: the values that
// scenario changes for one attribute.
export function ScenarioChangeDrawer() {
  const mainBounds = useMainBounds();
  const content = useProjectStore((s) => s.scenarioChange);
  const record = useProjectStore((s) => s.record);
  const closeScenarioChange = useProjectStore((s) => s.closeScenarioChange);
  const title = content
    ? `${
        record?.info.revisions.find((revision) => revision.name === content.scenario)?.label ??
        content.scenario
      } · ${content.attribute}`
    : "";

  return (
    <Drawer.Root
      open={content !== null}
      onOpenChange={(open) => {
        if (!open) closeScenarioChange();
      }}
      modal={false}
      disablePointerDismissal
      snapPoints={SNAP_POINTS}
      defaultSnapPoint={SNAP_POINTS[1]}
      snapToSequentialPoints
    >
      <Drawer.Portal>
        <Drawer.Viewport
          className="pointer-events-none fixed inset-0 z-30 flex touch-none items-end justify-center"
          style={mainBounds ? { left: mainBounds.left, right: mainBounds.right } : undefined}
        >
          <Drawer.Popup className="drawer-popup border-surface-600 bg-surface-800 pointer-events-auto relative flex max-h-[92vh] w-full touch-none flex-col rounded-t-lg border-t shadow-2xl shadow-black/50 outline-none">
            <div className="bg-surface-600 hover:bg-accent-500 mx-auto mt-1.5 h-1 w-10 shrink-0 cursor-row-resize touch-none rounded-full transition-colors" />
            <div className="border-surface-600 flex h-8 shrink-0 cursor-row-resize touch-none items-center justify-between border-b px-3 select-none">
              <div className="text-surface-200 flex min-w-0 items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
                <LuGitCompareArrows size={12} className="shrink-0" />
                <span className="truncate" title={title}>
                  {title}
                </span>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <Drawer.Close className="text-surface-400 hover:text-surface-100 outline-none">
                  <LuX size={14} />
                </Drawer.Close>
              </div>
            </div>
            <Drawer.Content className="min-h-0 flex-1 touch-auto overflow-y-auto overscroll-contain text-[12px]">
              {content && (
                <ScenarioChangeTable
                  key={`${content.scenario}\n${content.attribute}`}
                  scenario={content.scenario}
                  attribute={content.attribute}
                />
              )}
            </Drawer.Content>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
