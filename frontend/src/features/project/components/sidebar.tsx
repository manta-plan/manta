import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useLocation } from "wouter";
import { Tooltip } from "@base-ui/react/tooltip";
import { GiMagnifyingGlass } from "react-icons/gi";
import { LuBoxes, LuChartBar, LuCircleCheck, LuLayers, LuListFilter, LuPlus } from "react-icons/lu";
import { ReportResultsPanel } from "../../report/components/report-results-panel";
import { ReportsPanel } from "../../report/components/reports-panel";
import { InspectionsPanel } from "../../inspect/components/inspections-panel";
import { getActiveProjectTab } from "../lib/project-route";
import { useProjectStore } from "../store/project-store";
import { SidebarPanel } from "./sidebar-panel";
import { ModelTreePanel } from "./model-tree-panel";
import { RecordScenariosPanel } from "./record-scenarios-panel";

const TOOLTIP_POPUP =
  "border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg";

function AddButton({
  label,
  onClick,
  tourId,
}: {
  label: string;
  onClick?: () => void;
  tourId?: string;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            aria-label={label}
            data-tour={tourId}
            onClick={onClick}
            onPointerDown={(event) => event.stopPropagation()}
            className="text-surface-400 hover:text-surface-100 outline-none"
          />
        }
      >
        <LuPlus size={13} />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className={TOOLTIP_POPUP}>{label}</Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

function FilterButton({
  label,
  onClick,
  isActive,
}: {
  label: string;
  onClick: () => void;
  isActive: boolean;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            aria-label={label}
            aria-pressed={isActive}
            onClick={onClick}
            onPointerDown={(event) => event.stopPropagation()}
            className={`outline-none ${isActive ? "text-accent-400" : "text-surface-400 hover:text-surface-100"}`}
          />
        }
      >
        <LuListFilter size={13} />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className={TOOLTIP_POPUP}>{label}</Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function Sidebar() {
  const sidebarRef = useRef<HTMLElement>(null);
  const [primaryPanelHeight, setPrimaryPanelHeight] = useState<number | null>(null);
  // The Record panel is titled with the project's record.
  const record = useProjectStore((s) => s.record);
  const [location] = useLocation();
  const activeTab = getActiveProjectTab(location);
  const openNewInspectionDrawer = useProjectStore((s) => s.openNewInspectionDrawer);
  const openInspectionFilterDrawer = useProjectStore((s) => s.openInspectionFilterDrawer);
  const isInspectionFilterDrawerOpen = useProjectStore((s) => s.isInspectionFilterDrawerOpen);
  const inspectionFilters = useProjectStore((s) => s.inspectionFilters);
  const openNewReportDrawer = useProjectStore((s) => s.openNewReportDrawer);
  const openReportFilterDrawer = useProjectStore((s) => s.openReportFilterDrawer);
  const isReportFilterDrawerOpen = useProjectStore((s) => s.isReportFilterDrawerOpen);
  const reportFilters = useProjectStore((s) => s.reportFilters);
  const updatePrimaryPanelHeight = (height: number) => {
    const sidebarHeight = sidebarRef.current?.clientHeight ?? 0;
    const minimumPanelHeight = 160;
    setPrimaryPanelHeight(
      Math.max(minimumPanelHeight, Math.min(height, sidebarHeight - minimumPanelHeight)),
    );
  };
  const resizeFromPointer = (event: PointerEvent<HTMLDivElement>) => {
    const top = sidebarRef.current?.getBoundingClientRect().top;
    if (top !== undefined) updatePrimaryPanelHeight(event.clientY - top);
  };
  const startResize = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeFromPointer(event);
  };
  const continueResize = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) resizeFromPointer(event);
  };
  const resizeFromKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const sidebarHeight = sidebarRef.current?.clientHeight ?? 0;
    const currentHeight = primaryPanelHeight ?? (sidebarHeight * 2) / 3;
    if (event.key === "Home") updatePrimaryPanelHeight(160);
    else if (event.key === "End") updatePrimaryPanelHeight(sidebarHeight - 160);
    else updatePrimaryPanelHeight(currentHeight + (event.key === "ArrowUp" ? -24 : 24));
  };

  // Inspections don't pick from the record, so their list takes the whole sidebar.
  if (activeTab === "inspect") {
    return (
      <aside
        ref={sidebarRef}
        data-tour="inspections-panel"
        className="border-surface-600 bg-surface-800 flex h-full w-72 shrink-0 flex-col overflow-hidden border-r"
      >
        <SidebarPanel
          icon={GiMagnifyingGlass}
          label="Inspections"
          action={
            <div className="flex items-center gap-2">
              <FilterButton
                label="Filter inspections"
                onClick={openInspectionFilterDrawer}
                isActive={isInspectionFilterDrawerOpen || inspectionFilters.length > 0}
              />
              <AddButton
                label="New Inspection"
                tourId="new-inspection-action"
                onClick={openNewInspectionDrawer}
              />
            </div>
          }
        >
          <InspectionsPanel />
        </SidebarPanel>
      </aside>
    );
  }

  return (
    <aside
      ref={sidebarRef}
      className="border-surface-600 bg-surface-800 flex h-full w-72 shrink-0 flex-col border-r"
    >
      <div
        data-tour={activeTab === "report" ? "reports-panel" : "model-tree-panel"}
        className="min-h-40 shrink-0 overflow-hidden"
        style={{
          height:
            primaryPanelHeight === null
              ? "66.6667%"
              : `clamp(10rem, ${primaryPanelHeight}px, calc(100% - 10rem))`,
        }}
      >
        {activeTab === "report" ? (
          <SidebarPanel
            icon={LuChartBar}
            label="Reports"
            action={
              <div className="flex items-center gap-2">
                <FilterButton
                  label="Filter reports"
                  onClick={openReportFilterDrawer}
                  isActive={isReportFilterDrawerOpen || reportFilters.length > 0}
                />
                <AddButton
                  label="New Report"
                  tourId="new-report-action"
                  onClick={() => openNewReportDrawer()}
                />
              </div>
            }
          >
            <ReportsPanel />
          </SidebarPanel>
        ) : (
          <SidebarPanel icon={LuBoxes} label={record?.info.label ?? "Record"}>
            <ModelTreePanel />
          </SidebarPanel>
        )}
      </div>
      <div
        role="separator"
        aria-label="Resize sidebar panels"
        aria-orientation="horizontal"
        tabIndex={0}
        onPointerDown={startResize}
        onPointerMove={continueResize}
        onKeyDown={resizeFromKeyboard}
        className="before:bg-surface-600 hover:before:bg-accent-500 focus-visible:before:bg-accent-500 relative h-1 shrink-0 cursor-row-resize touch-none outline-none before:absolute before:top-0 before:right-0 before:left-0 before:h-px before:transition-colors"
      />
      <div
        data-tour={activeTab === "report" ? "scenario-runs-panel" : undefined}
        className="min-h-40 flex-1 overflow-hidden"
      >
        {activeTab === "report" ? (
          <SidebarPanel
            icon={LuCircleCheck}
            label="Run Results"
            onHeaderPointerDown={startResize}
            onHeaderPointerMove={continueResize}
          >
            <ReportResultsPanel />
          </SidebarPanel>
        ) : (
          <SidebarPanel
            icon={LuLayers}
            label="Scenarios"
            onHeaderPointerDown={startResize}
            onHeaderPointerMove={continueResize}
          >
            <RecordScenariosPanel />
          </SidebarPanel>
        )}
      </div>
    </aside>
  );
}
