// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import {
  useEffect,
  useMemo,
  useRef,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import { LuChevronRight, LuCircleDot, LuLayers, LuMapPin } from "react-icons/lu";
import { useShownData } from "../project/lib/record-data";
import { serverQuery } from "../project/lib/record-server/client";
import { getEntityListItem } from "../project/lib/record-server/queries";
import type { InspectResult } from "../project/lib/record-results";
import { Segmented } from "../../components/segmented";
import { useOpenRecordPage } from "../project/lib/use-record-page";
import { useProjectStore } from "../project/store/project-store";
import { ALL_ENTITIES, ALL_LOCATIONS, levelPageId, type Level } from "./level";
import { LevelPageContext, useLevelPage, type LevelPageValue } from "./level-page-context";
import { levelCtes, scopeKey } from "./level-sql";
import {
  SPLIT_HEIGHT_DEFAULT,
  SPLIT_HEIGHT_MAX,
  SPLIT_HEIGHT_MIN,
  SPLIT_RATIO_DEFAULT,
  useLevelStore,
} from "./level-store";
import { useLevelScope, usePeriods } from "./periods";
import { BlockFullscreenDialog, BlockSlot } from "./fullscreen/block-fullscreen";
import { LevelTiles } from "./tiles/level-tiles";
import { TimeWindowButton } from "./time-window-button";

// One page per level, the same at every level: the page head (investment
// period, breadcrumb and title, count, source, time window), the stat tiles,
// then the split — the members table beside the map or graph, one height —
// and the chart drawer under it, whose handle drags the split's height.

export function LevelPage({
  level,
  stage,
  result,
}: {
  level: Level;
  stage: "build" | "inspect";
  result: InspectResult | null;
}) {
  const openPage = useOpenRecordPage();
  const scope = useLevelScope(level);
  const resetForLevel = useLevelStore((s) => s.resetForLevel);
  const pageId = levelPageId(level);
  // What belongs to the last level (filters, sort, focus, picks) goes.
  useEffect(() => resetForLevel(), [pageId, resetForLevel]);

  const value = useMemo<LevelPageValue>(
    () => ({ level, stage, result, scope, openLevel: (next) => openPage(levelPageId(next)) }),
    // scope is rebuilt each render; its key says when it changed.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
    [pageId, stage, result, scope && scopeKey(scope), openPage],
  );

  return (
    <LevelPageContext.Provider value={value}>
      <div
        data-tour="inspect-main-section"
        className="bg-surface-900 flex h-full min-w-0 flex-col overflow-hidden"
      >
        <PageHead />
        <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pt-3">
          <PeriodsError />
          <LevelTiles />
          <Split />
          <DrawerHandle />
          <BlockFullscreenDialog />
          <section
            aria-label="Chart"
            className="border-surface-700 bg-surface-900 min-h-[18rem] shrink-0 border border-b-0"
          >
            <BlockSlot block="chart" />
          </section>
        </main>
      </div>
    </LevelPageContext.Provider>
  );
}

// ------------------------------------------------------------ Page head

function PageHead() {
  return (
    <header className="border-surface-700 bg-surface-800 flex shrink-0 flex-col gap-1.5 border-b px-4 pt-2.5 pb-3">
      <Breadcrumb />
      {/* The level on the left; on the right the time slice it's read for:
          the investment period, then the window inside it. One centre line;
          on a narrow page the filters wrap under the title as a group. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-[1_1_20rem] items-center gap-3">
          <Title />
          <CountPill />
          <SourceNote />
        </div>
        <div className="ml-auto flex max-w-full min-w-0 flex-wrap items-center justify-end gap-2">
          <PeriodControl />
          <TimeWindowButton />
        </div>
      </div>
    </header>
  );
}

/** Every read waits for the periods: if they can't be read, say so rather than load forever. */
function PeriodsError() {
  const { error } = usePeriods();
  if (!error) return null;
  return (
    <div
      role="alert"
      className="border-danger-500/40 bg-danger-500/10 text-danger-300 shrink-0 border px-3 py-2 text-[12px]"
    >
      Couldn't read the record's investment periods, so this page can't load:{" "}
      <span className="font-mono text-[11px]">{error}</span>
    </div>
  );
}

function PeriodControl() {
  const { periods, period } = usePeriods();
  const setPeriod = useLevelStore((s) => s.setPeriod);
  if (periods.length === 0 || period === null) return <div className="h-8" />;
  // Equal columns, so any number of periods lines up; many scroll in the track.
  return (
    <Segmented
      variant="underline"
      size="md"
      equal
      ariaLabel="Investment period"
      value={period}
      onChange={setPeriod}
      options={periods.map((item) => ({
        value: item.period,
        label: item.period,
        title: `Show the entities active in ${item.period}: build_year ≤ ${item.period} < build_year + lifetime`,
      }))}
      suffix={
        <span className="flex items-center gap-1.5">
          <LuLayers size={13} aria-hidden />
          <span className="text-[10px] leading-none font-medium tracking-wide uppercase max-sm:hidden">
            Investment period
          </span>
        </span>
      }
    />
  );
}

/** The entity's type and carrier, for its breadcrumb and title. */
function useEntityPlace(level: Level) {
  const entity = level.kind === "entity" ? level.entity : null;
  const data = useShownData("level-entity-place", entity === null ? null : [entity], () =>
    getEntityListItem(entity!),
  );
  return data.status === "ready" ? data.data : null;
}

function Breadcrumb() {
  const { level, openLevel } = useLevelPage();
  const carriers = useProjectStore((s) => s.record?.carriers);
  const recordLabel = useProjectStore((s) => s.record?.info.label ?? "Record");
  const place = useEntityPlace(level);
  const crumbs: { label: string; level: Level }[] = [];
  const carrierLabel = (carrier: string) => carriers?.[carrier]?.niceName || carrier;
  switch (level.kind) {
    case "all-entities":
    case "all-locations":
      break;
    case "component":
      crumbs.push({ label: "All entities", level: ALL_ENTITIES });
      break;
    case "carrier":
      crumbs.push(
        { label: "All entities", level: ALL_ENTITIES },
        { label: level.ctype, level: { kind: "component", ctype: level.ctype } },
      );
      break;
    case "entity":
      crumbs.push({ label: "All entities", level: ALL_ENTITIES });
      if (place) {
        crumbs.push({ label: place.ctype, level: { kind: "component", ctype: place.ctype } });
        if (place.carrier)
          crumbs.push({
            label: carrierLabel(place.carrier),
            level: { kind: "carrier", ctype: place.ctype, carrier: place.carrier },
          });
      }
      break;
    case "location":
      crumbs.push({ label: "All locations", level: ALL_LOCATIONS });
      break;
    case "bus":
      crumbs.push({ label: "All locations", level: ALL_LOCATIONS });
      if (level.location)
        crumbs.push({
          label: level.location,
          level: { kind: "location", location: level.location },
        });
      break;
  }
  // Always there, starting at the record, so the title row never moves
  // between the root pages and the ones under them.
  return (
    <nav
      aria-label="Breadcrumb"
      className="text-surface-400 flex h-4 min-w-0 items-center gap-1 text-[11px]"
    >
      <span className="flex min-w-0 items-center gap-1">
        <span className="text-surface-500 truncate px-0.5">{recordLabel}</span>
        <LuChevronRight size={11} className="text-surface-600 shrink-0" />
      </span>
      {crumbs.map((crumb) => (
        <span key={levelPageId(crumb.level) ?? "root"} className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => openLevel(crumb.level)}
            className="hover:text-surface-100 focus-visible:ring-accent-500 truncate rounded px-0.5 outline-none hover:underline focus-visible:ring-1"
          >
            {crumb.label}
          </button>
          <LuChevronRight size={11} className="text-surface-600 shrink-0" />
        </span>
      ))}
    </nav>
  );
}

function Dot({ color }: { color: string | null | undefined }) {
  return (
    <span
      className="h-2.5 w-2.5 shrink-0 rounded-full border border-black/20"
      style={{ backgroundColor: color ?? "var(--color-surface-500)" }}
    />
  );
}

function Title() {
  const { level } = useLevelPage();
  const record = useProjectStore((s) => s.record);
  const place = useEntityPlace(level);
  const carrier = (name: string | null | undefined) => (name ? record?.carriers[name] : undefined);
  const regionOf = (location: string) =>
    record?.zones.find((zone) => zone.location === location)?.zone ?? null;
  let content: ReactNode;
  switch (level.kind) {
    case "all-entities":
      content = <Name>All entities</Name>;
      break;
    case "all-locations":
      content = <Name>All locations</Name>;
      break;
    case "component":
      content = <Name>{level.ctype}</Name>;
      break;
    case "carrier":
      content = (
        <>
          <Dot color={carrier(level.carrier)?.color} />
          <Name>{carrier(level.carrier)?.niceName || level.carrier}</Name>
          <span className="text-surface-400 shrink-0 font-normal">{level.ctype}</span>
        </>
      );
      break;
    case "entity":
      content = (
        <>
          <Dot color={carrier(place?.carrier)?.color} />
          <Name>{level.entity}</Name>
        </>
      );
      break;
    case "location": {
      const region = regionOf(level.location);
      content = (
        <>
          <LuMapPin size={15} className="text-accent-400 shrink-0" />
          <Name>{level.location}</Name>
          {region && (
            <span className="border-surface-600 text-surface-300 shrink-0 rounded-full border px-2 text-[11px] font-normal">
              {region}
            </span>
          )}
        </>
      );
      break;
    }
    case "bus":
      content = (
        <>
          <LuCircleDot size={14} className="text-accent-400 shrink-0" />
          <Name>{level.bus}</Name>
        </>
      );
      break;
  }
  return (
    <h1 className="text-surface-50 flex min-w-0 items-center gap-2 text-[16px] font-semibold">
      {content}
    </h1>
  );
}

/** The level's name in the title: the part that gives way, with an ellipsis and the whole name on hover. */
function Name({ children }: { children: string }) {
  return (
    <span title={children} className="min-w-0 truncate">
      {children}
    </span>
  );
}

function CountPill() {
  const { level, scope } = useLevelPage();
  const locations = useProjectStore((s) => s.record?.locations.length ?? 0);
  const isAllLocations = level.kind === "all-locations";
  const data = useShownData(
    "level-count",
    scope && !isAllLocations ? [scopeKey(scope)] : null,
    async () => {
      const rows = await serverQuery<{ n: number }>(
        `WITH ${levelCtes(scope!)} SELECT count(*)::INTEGER AS n FROM members`,
      );
      return rows[0]?.n ?? 0;
    },
  );
  const text = isAllLocations
    ? `${locations.toLocaleString()} locations`
    : data.status === "ready"
      ? `${data.data.toLocaleString()} ${data.data === 1 ? "entity" : "entities"}`
      : null;
  if (text === null || level.kind === "entity") return null;
  return (
    <span
      className={`border-surface-600 text-surface-300 shrink-0 rounded-full border px-2 text-[11px] whitespace-nowrap ${data.status === "ready" && data.refreshing ? "opacity-60" : ""}`}
    >
      {text}
    </span>
  );
}

function SourceNote() {
  const { stage, result } = useLevelPage();
  const record = useProjectStore((s) => s.record);
  if (!record) return null;
  const shown = record.info.revisions.find((revision) => revision.name === record.scenario);
  const inputs = result ? result.scenarioLabel : (shown?.label ?? record.info.label);
  return (
    <span className="text-surface-500 min-w-0 truncate text-[11px]">
      Inputs from <span className="text-surface-300">{inputs}</span>
      {stage === "inspect" && result && (
        <>
          {" "}
          · results of <span className="text-surface-300">{result.label}</span>
        </>
      )}
    </span>
  );
}

// ------------------------------------------------------------ Split

const KEY_STEP = 40;

function Split() {
  const height = useLevelStore((s) => s.splitHeight);
  const ratio = useLevelStore((s) => s.splitRatio);
  const setRatio = useLevelStore((s) => s.setSplitRatio);
  const isSideOpen = useLevelStore((s) => s.isMapGraphOpen);
  const ref = useRef<HTMLDivElement>(null);

  const ratioAt = (clientX: number) => {
    const box = ref.current?.getBoundingClientRect();
    return box && box.width > 0 ? (clientX - box.left) / box.width : ratio;
  };
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) setRatio(ratioAt(event.clientX));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    setRatio(ratio + (event.key === "ArrowLeft" ? -0.02 : 0.02));
  };

  return (
    <div
      ref={ref}
      className="flex shrink-0 max-[860px]:flex-col max-[860px]:gap-3"
      style={{ height: `var(--split-height, ${height}px)` }}
    >
      <section
        aria-label="Members"
        className="border-surface-700 bg-surface-900 min-w-0 overflow-hidden border max-[860px]:h-[340px]"
        style={{ flex: isSideOpen ? `0 0 ${ratio * 100}%` : "1 1 auto" }}
      >
        <BlockSlot block="table" />
      </section>
      {isSideOpen && (
        <>
          <div
            role="separator"
            aria-label="Resize the table and the map"
            aria-orientation="vertical"
            aria-valuenow={Math.round(ratio * 100)}
            tabIndex={0}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onKeyDown={onKeyDown}
            onDoubleClick={() => setRatio(SPLIT_RATIO_DEFAULT)}
            className="group relative w-3 shrink-0 cursor-col-resize touch-none outline-none max-[860px]:hidden"
          >
            <span className="bg-surface-700 group-hover:bg-accent-500 group-focus-visible:bg-accent-500 absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors" />
          </div>
          <section
            aria-label="Map and graph"
            className="border-surface-700 bg-surface-900 min-w-0 flex-1 overflow-hidden border max-[860px]:h-[320px]"
          >
            <BlockSlot block="map-graph" />
          </section>
        </>
      )}
    </div>
  );
}

/** The chart drawer's grab handle: drags the split's height (double-click resets; arrows step; Home/End jump to the limits). */
function DrawerHandle() {
  const height = useLevelStore((s) => s.splitHeight);
  const setHeight = useLevelStore((s) => s.setSplitHeight);
  const start = useRef<{ y: number; height: number } | null>(null);
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    start.current = { y: event.clientY, height };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (start.current && event.currentTarget.hasPointerCapture(event.pointerId))
      setHeight(start.current.height + event.clientY - start.current.y);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = {
      ArrowUp: height - KEY_STEP,
      ArrowDown: height + KEY_STEP,
      Home: SPLIT_HEIGHT_MIN,
      End: SPLIT_HEIGHT_MAX,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    setHeight(next);
  };
  return (
    <div
      role="separator"
      aria-label="Resize the table and map height"
      aria-orientation="horizontal"
      aria-valuenow={height}
      aria-valuemin={SPLIT_HEIGHT_MIN}
      aria-valuemax={SPLIT_HEIGHT_MAX}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={() => (start.current = null)}
      onKeyDown={onKeyDown}
      onDoubleClick={() => setHeight(SPLIT_HEIGHT_DEFAULT)}
      className="group -my-1.5 flex h-3 shrink-0 cursor-row-resize touch-none items-center justify-center outline-none max-[860px]:hidden"
    >
      <span className="bg-surface-600 group-hover:bg-accent-500 group-focus-visible:bg-accent-500 h-1 w-10 rounded-full transition-colors" />
    </div>
  );
}
