import { useEffect, useState } from "react";
import { Menu } from "@base-ui/react/menu";
import { Tooltip } from "@base-ui/react/tooltip";
import { LuCheck, LuPlus, LuSquarePlus } from "react-icons/lu";
import { useProjectStore } from "../../project/store/project-store";
import { useInspectionActions, useWidgetItem } from "../../project/lib/widget-set-context";
import { WidgetTooltipPopup } from "./widget-icon-button";

const itemClassName =
  "flex cursor-default items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:bg-accent-600 data-[highlighted]:text-white";
const groupLabelClassName =
  "px-3 pt-1 pb-1.5 text-[10px] font-medium uppercase tracking-wide text-surface-400";

// Sends a widget to a report (dummy for now: it only confirms) or to one of
// the user's inspections.
export function AddToMenu({ widgetName }: { widgetName: string }) {
  const reports = useProjectStore((s) => s.reports);
  const inspections = useProjectStore((s) => s.inspections);
  const widgetItem = useWidgetItem();
  const actions = useInspectionActions();
  const [addedTo, setAddedTo] = useState<string | null>(null);
  const targets = inspections.filter(
    (inspection) => inspection.id !== actions?.currentInspectionId,
  );

  useEffect(() => {
    if (!addedTo) return;
    const timeout = setTimeout(() => setAddedTo(null), 2000);
    return () => clearTimeout(timeout);
  }, [addedTo]);

  return (
    <Tooltip.Root>
      <Menu.Root>
        <Tooltip.Trigger
          render={
            <Menu.Trigger
              aria-label={`Add ${widgetName} to…`}
              className={`data-[popup-open]:bg-surface-700 data-[popup-open]:text-surface-50 flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none ${
                addedTo
                  ? "text-ok-500"
                  : "text-surface-400 hover:bg-surface-700 hover:text-surface-50"
              }`}
            />
          }
        >
          {addedTo ? <LuCheck size={14} /> : <LuSquarePlus size={14} />}
        </Tooltip.Trigger>
        <Menu.Portal>
          <Menu.Positioner className="z-50 outline-none" sideOffset={4} align="end">
            <Menu.Popup className="border-surface-600 bg-surface-800 text-surface-100 max-w-64 min-w-52 rounded-md border py-1 text-[12px] shadow-2xl shadow-black/50 outline-none">
              <Menu.Group>
                <Menu.GroupLabel className={groupLabelClassName}>Report</Menu.GroupLabel>
                {reports.length > 0 ? (
                  reports.map((report) => (
                    <Menu.Item
                      key={report.id}
                      onClick={() => setAddedTo(report.name)}
                      className={itemClassName}
                    >
                      <span className="min-w-0 flex-1 truncate">{report.name}</span>
                    </Menu.Item>
                  ))
                ) : (
                  <div className="text-surface-500 px-3 py-1.5">No reports yet</div>
                )}
              </Menu.Group>
              {widgetItem && actions && (
                <>
                  <Menu.Separator className="bg-surface-600 my-1 h-px" />
                  <Menu.Group>
                    <Menu.GroupLabel className={groupLabelClassName}>Inspection</Menu.GroupLabel>
                    {targets.map((inspection) => (
                      <Menu.Item
                        key={inspection.id}
                        onClick={() => {
                          actions.addToInspection(inspection.id, widgetItem.item);
                          setAddedTo(inspection.name);
                        }}
                        className={itemClassName}
                      >
                        <span className="min-w-0 flex-1 truncate">{inspection.name}</span>
                      </Menu.Item>
                    ))}
                    <Menu.Item
                      onClick={() => actions.addToNewInspection(widgetItem.item)}
                      className={`${itemClassName} text-accent-300`}
                    >
                      <LuPlus size={12} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate">New inspection…</span>
                    </Menu.Item>
                  </Menu.Group>
                </>
              )}
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
      <WidgetTooltipPopup label={addedTo ? `Added to ${addedTo}` : "Add to…"} />
    </Tooltip.Root>
  );
}
