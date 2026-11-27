// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Tooltip } from "@base-ui/react/tooltip";
import { GiMagnifyingGlass } from "react-icons/gi";
import { LuChartBar, LuDatabase, LuPlus, LuSearch } from "react-icons/lu";
import { SidebarPanel } from "../../project/components/sidebar-panel";
import { useProjectStore } from "../../project/store/project-store";
import { DataPanel } from "./data-panel";
import { InspectionsPanel } from "./inspections-panel";
import { ReportsPanel } from "./reports-panel";

// Data, Views and Reports at 1:2:1, so Views stays the main list.
const DEFAULT_TOP_SHARE = 75;
const MINIMUM_REPORTS_HEIGHT = 160;
const MINIMUM_DATA_VIEWS_HEIGHT = 96;
const SEPARATOR_HEIGHT = 4;
// Data and Views each keep their minimum, with the separator between them.
const MINIMUM_TOP_HEIGHT = 2 * MINIMUM_DATA_VIEWS_HEIGHT + SEPARATOR_HEIGHT;

const tooltipPopupClassName =
  "border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg";

function HeaderButton({
  label,
  tourId,
  isPressed,
  onClick,
  children,
}: {
  label: string;
  tourId?: string;
  isPressed?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            aria-label={label}
            aria-pressed={isPressed}
            data-tour={tourId}
            onClick={onClick}
            onPointerDown={(event) => event.stopPropagation()}
            className={`focus-visible:ring-accent-500 rounded outline-none focus-visible:ring-1 ${isPressed ? "text-accent-400" : "text-surface-400 hover:text-surface-100"}`}
          />
        }
      >
        {children}
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className={tooltipPopupClassName}>{label}</Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

const separatorClassName =
  "before:bg-surface-600 hover:before:bg-accent-500 focus-visible:before:bg-accent-500 relative h-1 shrink-0 cursor-row-resize touch-none outline-none before:absolute before:top-0 before:right-0 before:left-0 before:h-px before:transition-colors";

/** A divider that resizes the panel above it, from a drag or the arrow keys. */
function useDivider(
  containerRef: React.RefObject<HTMLElement | null>,
  /** The least the panel above may be, and the least left below. */
  minimumAbove: number,
  minimumBelow: number,
  share: number,
) {
  const [height, setHeight] = useState<number | null>(null);
  const update = (next: number) => {
    const total = containerRef.current?.clientHeight ?? 0;
    setHeight(Math.max(minimumAbove, Math.min(next, total - minimumBelow)));
  };
  const fromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const top = containerRef.current?.getBoundingClientRect().top;
    if (top !== undefined) update(event.clientY - top);
  };
  return {
    height,
    handlers: {
      onPointerDown: (event: PointerEvent<HTMLDivElement>) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        fromPointer(event);
      },
      onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) fromPointer(event);
      },
    },
    onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
      if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const total = containerRef.current?.clientHeight ?? 0;
      const current = height ?? total * share;
      if (event.key === "Home") update(minimumAbove);
      else if (event.key === "End") update(total - minimumBelow);
      else update(current + (event.key === "ArrowUp" ? -24 : 24));
    },
  };
}

// The Analyse tab: Data (what there is to chart), Views (pages of widgets
// that chart it) and Reports (paper pages of widgets).
export function AnalyseSidebar() {
  const sidebarRef = useRef<HTMLElement>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const [isFindingData, setFindingData] = useState(false);
  const [isFindingView, setFindingView] = useState(false);
  const openNewReportDrawer = useProjectStore((s) => s.openNewReportDrawer);
  const openNewInspectionDrawer = useProjectStore((s) => s.openNewInspectionDrawer);
  const primary = useDivider(
    sidebarRef,
    MINIMUM_TOP_HEIGHT,
    MINIMUM_REPORTS_HEIGHT + SEPARATOR_HEIGHT,
    DEFAULT_TOP_SHARE / 100,
  );
  // Data starts at a third of the top part (1 of Data:Views 1:2).
  const data = useDivider(topRef, MINIMUM_DATA_VIEWS_HEIGHT, MINIMUM_DATA_VIEWS_HEIGHT, 1 / 3);

  return (
    <aside
      ref={sidebarRef}
      className="border-surface-600 bg-surface-800 flex h-full w-72 shrink-0 flex-col border-r"
    >
      <div
        className="shrink-0 overflow-hidden"
        style={{
          height: `clamp(${MINIMUM_TOP_HEIGHT}px, ${primary.height === null ? `${DEFAULT_TOP_SHARE}%` : `${primary.height}px`}, calc(100% - ${MINIMUM_REPORTS_HEIGHT + SEPARATOR_HEIGHT}px))`,
        }}
      >
        <div ref={topRef} className="flex h-full flex-col">
          <div
            data-tour="data-panel"
            className={`min-h-24 overflow-hidden ${data.height === null ? "flex-[1]" : "shrink-0"}`}
            style={
              data.height === null
                ? undefined
                : { height: `clamp(6rem, ${data.height}px, calc(100% - 6rem))` }
            }
          >
            <SidebarPanel
              icon={LuDatabase}
              label="Data"
              action={
                <HeaderButton
                  label={isFindingData ? "Hide search" : "Find a table"}
                  isPressed={isFindingData}
                  onClick={() => setFindingData((open) => !open)}
                >
                  <LuSearch size={13} />
                </HeaderButton>
              }
            >
              <DataPanel showSearch={isFindingData} />
            </SidebarPanel>
          </div>
          <div
            role="separator"
            aria-label="Resize the Data and Views panels"
            aria-orientation="horizontal"
            tabIndex={0}
            {...data.handlers}
            onKeyDown={data.onKeyDown}
            className={separatorClassName}
          />
          <div
            data-tour="views-panel"
            className={`min-h-24 overflow-hidden ${data.height === null ? "flex-[2]" : "flex-1"}`}
          >
            <SidebarPanel
              icon={GiMagnifyingGlass}
              label="Views"
              action={
                <div className="flex items-center gap-2">
                  <HeaderButton
                    label={isFindingView ? "Hide search" : "Find a view"}
                    isPressed={isFindingView}
                    onClick={() => setFindingView((open) => !open)}
                  >
                    <LuSearch size={13} />
                  </HeaderButton>
                  <HeaderButton
                    label="New view"
                    tourId="new-inspection-action"
                    onClick={openNewInspectionDrawer}
                  >
                    <LuPlus size={13} />
                  </HeaderButton>
                </div>
              }
              onHeaderPointerDown={data.handlers.onPointerDown}
              onHeaderPointerMove={data.handlers.onPointerMove}
            >
              <InspectionsPanel showSearch={isFindingView} />
            </SidebarPanel>
          </div>
        </div>
      </div>
      <div
        role="separator"
        aria-label="Resize sidebar panels"
        aria-orientation="horizontal"
        tabIndex={0}
        {...primary.handlers}
        onKeyDown={primary.onKeyDown}
        className={separatorClassName}
      />
      <div data-tour="reports-panel" className="min-h-40 flex-1 overflow-hidden">
        <SidebarPanel
          icon={LuChartBar}
          label="Reports"
          action={
            <HeaderButton
              label="New report"
              tourId="new-report-action"
              onClick={() => openNewReportDrawer()}
            >
              <LuPlus size={13} />
            </HeaderButton>
          }
          onHeaderPointerDown={primary.handlers.onPointerDown}
          onHeaderPointerMove={primary.handlers.onPointerMove}
        >
          <ReportsPanel />
        </SidebarPanel>
      </div>
    </aside>
  );
}
