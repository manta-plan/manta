import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { LuBoxes, LuLayers } from "react-icons/lu";
import { useProjectStore } from "../store/project-store";
import { SidebarPanel } from "./sidebar-panel";
import { ModelTreePanel } from "./model-tree-panel";
import { RecordScenariosPanel } from "./record-scenarios-panel";

export function Sidebar() {
  const sidebarRef = useRef<HTMLElement>(null);
  const [primaryPanelHeight, setPrimaryPanelHeight] = useState<number | null>(null);
  // The Record panel is titled with the project's record.
  const record = useProjectStore((s) => s.record);
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

  return (
    <aside
      ref={sidebarRef}
      className="border-surface-600 bg-surface-800 flex h-full w-72 shrink-0 flex-col border-r"
    >
      <div
        data-tour="model-tree-panel"
        className="min-h-40 shrink-0 overflow-hidden"
        style={{
          height:
            primaryPanelHeight === null
              ? "66.6667%"
              : `clamp(10rem, ${primaryPanelHeight}px, calc(100% - 10rem))`,
        }}
      >
        <SidebarPanel icon={LuBoxes} label={record?.info.label ?? "Record"}>
          <ModelTreePanel />
        </SidebarPanel>
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
      <div className="min-h-40 flex-1 overflow-hidden">
        <SidebarPanel
          icon={LuLayers}
          label="Scenarios"
          onHeaderPointerDown={startResize}
          onHeaderPointerMove={continueResize}
        >
          <RecordScenariosPanel />
        </SidebarPanel>
      </div>
    </aside>
  );
}
