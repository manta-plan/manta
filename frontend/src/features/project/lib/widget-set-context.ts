import { createContext, useContext, useEffect, type RefObject } from "react";
import type { WidgetSetItem } from "./widget-sets";

// What a widget card needs from the inspection page to offer its own
// actions: the item it renders, how to remove it, and where it can go.

export interface WidgetItemContextValue {
  item: WidgetSetItem;
  onRemove: () => void;
  /** For built-ins a custom widget can rebuild: adds that copy after it, open for editing. */
  onEditCopy?: () => void;
  /** Moving the widget on the page, by its header's grip. */
  reorder?: {
    onDragStart: () => void;
    onDragEnd: () => void;
    /** One place earlier (-1) or later (1). */
    onStep: (direction: -1 | 1) => void;
  };
}

export const WidgetItemContext = createContext<WidgetItemContextValue | null>(null);

export function useWidgetItem() {
  return useContext(WidgetItemContext);
}

export interface InspectionActionsValue {
  /** The inspection on the page: a built-in id or one of the user's. */
  currentInspectionId: string;
  addToInspection: (inspectionId: string, item: WidgetSetItem) => void;
  /** Asks for a name, then saves a new inspection holding just this item. */
  addToNewInspection: (item: WidgetSetItem) => void;
}

export const InspectionActionsContext = createContext<InspectionActionsValue | null>(null);

export function useInspectionActions() {
  return useContext(InspectionActionsContext);
}

// The inspection page's data drawer: which widget it shows, and the element
// that widget renders its table into, so the table stays live.
export interface WidgetDataDrawerValue {
  openItemId: string | null;
  target: HTMLElement | null;
  toggle: (itemId: string) => void;
  close: () => void;
}

export const WidgetDataDrawerContext = createContext<WidgetDataDrawerValue | null>(null);

/** The data drawer as the current widget sees it; null outside an inspection. */
export function useWidgetDataDrawer() {
  const drawer = useContext(WidgetDataDrawerContext);
  const widgetItem = useContext(WidgetItemContext);
  if (!drawer || !widgetItem) return null;
  const itemId = widgetItem.item.id;
  return {
    isOpen: drawer.openItemId === itemId,
    target: drawer.target,
    toggle: () => drawer.toggle(itemId),
    close: drawer.close,
  };
}

// Keeps the widget whose data is open in sight above the drawer.
export function useScrollIntoViewWhen(ref: RefObject<HTMLElement | null>, isActive: boolean) {
  useEffect(() => {
    if (isActive) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [ref, isActive]);
}
