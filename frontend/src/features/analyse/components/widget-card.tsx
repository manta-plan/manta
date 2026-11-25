import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { LuPencilLine, LuX } from "react-icons/lu";
import type { FilterDimension } from "../lib/inspect-filters";
import {
  useScrollIntoViewWhen,
  useWidgetDataDrawer,
  useWidgetItem,
} from "../lib/widget-set-context";
import { useWidgetPresentation } from "../lib/widget-presentation";
import type { WidgetData } from "../lib/widget-data";
import { compareWidgetData, useComparison } from "../lib/result-comparison";
import { AddToMenu } from "./add-to-menu";
import { FilterNote } from "./filter-note";
import { WidgetDataButton } from "./widget-data-drawer";
import { WidgetIconButton } from "./widget-icon-button";
import { WidgetDragHandle } from "./widget-reorder";
import { WidgetBody } from "../../../components/widget-states";
import type { LoadState } from "../lib/use-result-data";

const SIZE_CLASS_NAMES = { compact: "h-44", regular: "h-[26rem]", tall: "h-[34rem]" };

// Full-width card holding one widget of an inspection.
// `filteredBy` lists the shared filters the widget applies to its data, and
// `data` is the table behind it, for the data drawer. `sidePanel` sits left
// of the content, for the custom widget's editor; `size` is the card height.
//
// When the page compares results, a built-in widget renders twice (see
// ComparedPresetWidget): the selected result's copy draws the card with two
// panels, and the compared copy renders only its body, into the right one.
export function WidgetCard({
  title,
  subtitle,
  action,
  filteredBy = [],
  data,
  sidePanel,
  size = "regular",
  loadState,
  children,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
  filteredBy?: FilterDimension[];
  data: WidgetData;
  sidePanel?: ReactNode;
  size?: keyof typeof SIZE_CLASS_NAMES;
  /** For widgets that query: their body shows loading, errors and refreshing for them. */
  loadState?: LoadState;
  children: ReactNode;
}) {
  const widgetItem = useWidgetItem();
  // In a report the card is just the widget: it fills its block and has no actions.
  const presentation = useWidgetPresentation();
  const isReport = presentation?.mode === "report";
  const isDataOpen = useWidgetDataDrawer()?.isOpen ?? false;
  const ref = useRef<HTMLElement>(null);
  useScrollIntoViewWhen(ref, isDataOpen);
  const comparison = useComparison();
  const isComparisonCopy = comparison?.role === "comparison";

  // The compared copy hands its table to the card, once per change of content.
  const dataKey = isComparisonCopy ? JSON.stringify(data) : "";
  const dataRef = useRef(data);
  dataRef.current = data;
  const setComparisonData = comparison?.setComparisonData;
  useEffect(() => {
    if (isComparisonCopy) setComparisonData?.(dataRef.current);
  }, [isComparisonCopy, setComparisonData, dataKey]);

  const shownData = useMemo(
    () =>
      comparison?.role === "primary" && comparison.comparisonData
        ? compareWidgetData(
            data,
            comparison.comparisonData,
            comparison.primaryName,
            comparison.comparisonName,
          )
        : data,
    [comparison, data],
  );

  const body = <WidgetBody state={loadState}>{children}</WidgetBody>;
  if (isComparisonCopy) return comparison.slot ? createPortal(body, comparison.slot) : null;
  const isCompared = comparison?.role === "primary";
  const shownTitle = presentation?.title
    ? `${presentation.title}${presentation.resultLabel ? `: ${presentation.resultLabel}` : ""}`
    : isCompared && title.endsWith(`: ${comparison.primaryName}`)
      ? `${title} vs ${comparison.comparisonName}`
      : title;

  return (
    <section
      ref={ref}
      data-editing={sidePanel ? "" : undefined}
      style={
        isReport
          ? {
              background: "var(--report-card-background)",
              borderColor: "var(--report-card-border)",
              borderRadius: "var(--report-card-radius)",
              boxShadow: "var(--report-card-shadow)",
            }
          : undefined
      }
      className={`bg-surface-900 flex w-full flex-col border p-4 ${isReport ? "h-full min-h-0" : `shrink-0 ${SIZE_CLASS_NAMES[size]}`} ${isDataOpen ? "border-accent-500" : "border-surface-700"}`}
    >
      <div className="border-surface-700 flex shrink-0 items-start justify-between gap-3 border-b pb-2">
        <div className="flex min-w-0 items-start gap-1.5">
          {!isReport && <WidgetDragHandle />}
          <div className="min-w-0">
            <div
              className="text-surface-100 truncate text-[12px] font-medium"
              style={isReport ? { fontFamily: "var(--report-font-heading)" } : undefined}
            >
              {shownTitle}
            </div>
            <div className="text-surface-400 truncate text-[11px]">{subtitle}</div>
          </div>
        </div>
        {!isReport && (
          <div className="flex shrink-0 items-center gap-2">
            <FilterNote filteredBy={filteredBy} />
            {action}
            {widgetItem?.onEditCopy && (
              <WidgetIconButton
                icon={LuPencilLine}
                label="Edit a copy"
                ariaLabel={`Edit a copy of ${title}`}
                onClick={widgetItem.onEditCopy}
              />
            )}
            <WidgetDataButton title={shownTitle} data={shownData} />
            <AddToMenu widgetName={title} />
            {widgetItem && (
              <WidgetIconButton
                icon={LuX}
                label="Remove widget"
                ariaLabel={`Remove ${title}`}
                onClick={widgetItem.onRemove}
              />
            )}
          </div>
        )}
      </div>
      <div className="flex min-h-0 flex-1">
        {!isReport && sidePanel}
        {isCompared ? (
          <div className="grid min-w-0 flex-1 grid-cols-2 gap-4 pt-2">
            <div className="flex min-h-0 min-w-0 flex-col">
              <div className="text-surface-300 mb-1 truncate text-[11px] font-medium">
                {comparison.primaryName}
              </div>
              <div className="relative min-h-0 flex-1">{body}</div>
            </div>
            <div className="flex min-h-0 min-w-0 flex-col">
              <div className="text-surface-300 mb-1 truncate text-[11px] font-medium">
                {comparison.comparisonName}
              </div>
              <div ref={comparison.setSlot} className="relative min-h-0 flex-1" />
            </div>
          </div>
        ) : (
          <div className="relative min-w-0 flex-1">{body}</div>
        )}
      </div>
    </section>
  );
}
