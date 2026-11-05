import { useRef, type DragEvent, type ReactNode } from "react";
import { Tooltip } from "@base-ui/react/tooltip";
import { LuGripVertical } from "react-icons/lu";
import { useWidgetItem } from "../../project/lib/widget-set-context";
import { WidgetTooltipPopup } from "./widget-icon-button";

// Reordering the widgets of an inspection: drag a widget by the grip in its
// header, or focus the grip and use the arrow keys. Only the grip starts a
// drag, so maps and charts keep their own panning and hovering.

export type DropPlacement = "before" | "after";

/**
 * One widget's place on the page. While another widget is dragged over it,
 * it shows where that widget will land: above or below it, or left or right
 * of it in a row of numbers (`axis="x"`).
 */
export function ReorderSlot({
  itemId,
  axis,
  draggingId,
  dropPlacement,
  onDragOverItem,
  onDropOnItem,
  className = "",
  children,
}: {
  itemId: string;
  axis: "x" | "y";
  draggingId: string | null;
  /** Where the dragged widget would land relative to this one, if it's over it. */
  dropPlacement: DropPlacement | null;
  onDragOverItem: (placement: DropPlacement) => void;
  onDropOnItem: (placement: DropPlacement) => void;
  className?: string;
  children: ReactNode;
}) {
  const placementOf = (event: DragEvent<HTMLDivElement>): DropPlacement => {
    const box = event.currentTarget.getBoundingClientRect();
    const isBefore =
      axis === "x"
        ? event.clientX < box.left + box.width / 2
        : event.clientY < box.top + box.height / 2;
    return isBefore ? "before" : "after";
  };
  const isTarget = draggingId !== null && draggingId !== itemId;

  return (
    <div
      data-reorder-slot={itemId}
      className={`relative flex min-w-0 shrink-0 flex-col ${draggingId === itemId ? "opacity-40" : ""} ${className}`}
      onDragOver={(event) => {
        if (!isTarget) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        onDragOverItem(placementOf(event));
      }}
      onDrop={(event) => {
        if (!isTarget) return;
        event.preventDefault();
        event.stopPropagation();
        onDropOnItem(placementOf(event));
      }}
    >
      {children}
      {isTarget &&
        dropPlacement && (
          // Centred in the 12px gap between widgets.
          <div
            aria-hidden
            className={`bg-accent-500 pointer-events-none absolute z-10 rounded-full ${
              axis === "x"
                ? `inset-y-0 w-0.5 ${dropPlacement === "before" ? "-left-[7px]" : "-right-[7px]"}`
                : `inset-x-0 h-0.5 ${dropPlacement === "before" ? "-top-[7px]" : "-bottom-[7px]"}`
            }`}
          />
        )}
    </div>
  );
}

/** The grip in a widget's header; renders nothing where widgets can't be reordered. */
export function WidgetDragHandle() {
  const widgetItem = useWidgetItem();
  const reorder = widgetItem?.reorder;
  const ref = useRef<HTMLSpanElement>(null);
  if (!widgetItem || !reorder) return null;
  const itemId = widgetItem.item.id;

  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <span
            ref={ref}
            role="button"
            data-drag-handle
            tabIndex={0}
            draggable
            aria-label="Move widget"
            aria-keyshortcuts="ArrowUp ArrowDown"
            onDragStart={(event) => {
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("text/plain", "");
              // Drag the whole widget, held where the grip is.
              const slot = ref.current?.closest<HTMLElement>("[data-reorder-slot]");
              if (slot) {
                const box = slot.getBoundingClientRect();
                event.dataTransfer.setDragImage(
                  slot,
                  event.clientX - box.left,
                  event.clientY - box.top,
                );
              }
              reorder.onDragStart();
            }}
            onDragEnd={reorder.onDragEnd}
            onKeyDown={(event) => {
              const direction =
                event.key === "ArrowUp" || event.key === "ArrowLeft"
                  ? -1
                  : event.key === "ArrowDown" || event.key === "ArrowRight"
                    ? 1
                    : 0;
              if (!direction) return;
              event.preventDefault();
              reorder.onStep(direction);
              // Moving a number in or out of a row redraws the widget; keep the grip focused.
              requestAnimationFrame(() =>
                document
                  .querySelector<HTMLElement>(`[data-reorder-slot="${itemId}"] [data-drag-handle]`)
                  ?.focus(),
              );
            }}
            className="text-surface-500 hover:bg-surface-700 hover:text-surface-100 focus-visible:bg-surface-700 focus-visible:text-surface-100 flex h-6 w-4 shrink-0 cursor-grab items-center justify-center rounded outline-none active:cursor-grabbing"
          />
        }
      >
        <LuGripVertical size={14} />
      </Tooltip.Trigger>
      <WidgetTooltipPopup label="Drag to move, or use the arrow keys" />
    </Tooltip.Root>
  );
}
