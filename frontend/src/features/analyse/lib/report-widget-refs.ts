import type { InspectionCanvas } from "../data/inspections";
import { BUILT_IN_INSPECTIONS } from "../data/inspections";
import type { WidgetRef } from "../data/reports";
import { PRESET_WIDGETS } from "../components/inspect-widget-registry";
import { copyWidgetItem, type WidgetSetItem } from "./widget-sets";

// What a report can place: the Inspect widgets of the built-in inspections
// and of the user's own, each as a reference to be resolved when it draws.

function itemLabel(item: WidgetSetItem): string | null {
  if (item.kind === "preset") return PRESET_WIDGETS[item.widgetId]?.label ?? null;
  if (item.kind === "custom") return item.title.trim() || "Custom widget";
  return null;
}

/** The widget's name, or null once it no longer exists. */
export function widgetRefLabel(ref: WidgetRef, inspections: InspectionCanvas[]): string | null {
  if (ref.source === "built-in") return PRESET_WIDGETS[ref.widgetId]?.label ?? null;
  if (ref.source === "detached") return itemLabel(ref.item);
  const item = inspections
    .find((inspection) => inspection.id === ref.inspectionId)
    ?.items.find((candidate) => candidate.id === ref.itemId);
  return item ? itemLabel(item) : null;
}

/** Where a referenced widget lives, for the block's settings: "Built-in" or the inspection's name. */
export function widgetRefSource(ref: WidgetRef, inspections: InspectionCanvas[]): string {
  if (ref.source === "built-in") return "Built-in widget";
  if (ref.source === "detached") return "Detached copy";
  return (
    inspections.find((inspection) => inspection.id === ref.inspectionId)?.name ??
    "Deleted inspection"
  );
}

export interface InsertableWidget {
  key: string;
  label: string;
  ref: WidgetRef;
}

export interface InsertableGroup {
  id: string;
  name: string;
  widgets: InsertableWidget[];
}

export function insertableWidgetGroups(inspections: InspectionCanvas[]): InsertableGroup[] {
  const builtIn = BUILT_IN_INSPECTIONS.map((inspection) => ({
    id: inspection.id,
    name: inspection.name,
    widgets: inspection.widgetIds
      .filter((widgetId) => PRESET_WIDGETS[widgetId])
      .map((widgetId) => ({
        key: `${inspection.id}/${widgetId}`,
        label: PRESET_WIDGETS[widgetId].label,
        ref: { source: "built-in", widgetId } as WidgetRef,
      })),
  }));
  const own = inspections.map((inspection) => ({
    id: inspection.id,
    name: inspection.name,
    widgets: inspection.items.flatMap((item) => {
      const label = itemLabel(item);
      return label
        ? [
            {
              key: `${inspection.id}/${item.id}`,
              label,
              ref: {
                source: "inspection",
                inspectionId: inspection.id,
                itemId: item.id,
              } as WidgetRef,
            },
          ]
        : [];
    }),
  }));
  // Single numbers for a report's summary; they're in no view.
  const keyFigures = {
    id: "key-figures",
    name: "Key figures",
    widgets: KEY_FIGURES.filter((widgetId) => PRESET_WIDGETS[widgetId]).map((widgetId) => ({
      key: `key-figures/${widgetId}`,
      label: PRESET_WIDGETS[widgetId].label,
      ref: { source: "built-in", widgetId } as WidgetRef,
    })),
  };
  return [keyFigures, ...builtIn, ...own].filter((group) => group.widgets.length > 0);
}

const KEY_FIGURES = ["total-cost", "total-supply", "total-emissions", "total-curtailment"];

/**
 * The widget a linked reference points at, as a copy the report can own, or
 * null when there's nothing to copy: it's already detached, or the widget
 * was deleted from its inspection. Built-in widgets can't change, so they
 * need no copy.
 */
export function detachedRef(ref: WidgetRef, inspections: InspectionCanvas[]): WidgetRef | null {
  if (ref.source !== "inspection") return null;
  const item = inspections
    .find((inspection) => inspection.id === ref.inspectionId)
    ?.items.find((candidate) => candidate.id === ref.itemId);
  return item ? { source: "detached", item: copyWidgetItem(item) } : null;
}
