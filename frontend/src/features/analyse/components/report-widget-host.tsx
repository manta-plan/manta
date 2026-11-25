import { useMemo, type ReactNode } from "react";
import type { BlockContent } from "../data/reports";
import { EMPTY_FILTERS, InspectFilterContext } from "../lib/inspect-filters";
import { ComparisonContext, ResultContext } from "../lib/result-comparison";
import { useResultCatalogue } from "../lib/use-result-data";
import type { ReportTheme } from "../data/report-themes";
import { WidgetPresentationContext } from "../lib/widget-presentation";
import { useProjectStore } from "../../project/store/project-store";
import { CustomWidget } from "./custom-widget";
import type { WidgetSetItem } from "../lib/widget-sets";
import { PRESET_WIDGETS } from "./inspect-widget-registry";

type WidgetBlockContent = Extract<BlockContent, { kind: "widget" }>;

function Unavailable({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="border-surface-600 flex h-full flex-col items-center justify-center gap-1 border border-dashed px-4 text-center">
      <div className="text-surface-200 text-[12px] font-medium">{title}</div>
      <div className="text-surface-400 text-[11px]">{detail}</div>
    </div>
  );
}

const noop = () => {};

/**
 * Draws the Inspect widget a report block references, on the run result the
 * block names. A widget is drawn by the same component the Inspect page uses;
 * the host only supplies what that page would: the result, no filters and no
 * comparison, with no card actions. Needs a ResultCatalogueContext above it.
 */
export function ReportWidgetHost({
  content,
  theme,
}: {
  content: WidgetBlockContent;
  theme: ReportTheme;
}) {
  const catalogue = useResultCatalogue();
  const inspections = useProjectStore((s) => s.inspections);
  const record = useProjectStore((s) => s.record);
  const allBuses = useMemo(
    () =>
      (record?.locations ?? [])
        .map((location) => location.location)
        .sort((a, b) => a.localeCompare(b)),
    [record],
  );
  const filterContext = useMemo(() => ({ filters: EMPTY_FILTERS, allBuses }), [allBuses]);

  const result = catalogue.results.find((run) => run.id === content.resultId);
  const presentation = useMemo(
    () => ({
      mode: "report" as const,
      scheme: theme.scheme,
      theme,
      title: content.title,
      resultLabel: result?.label,
    }),
    [theme, content.title, result?.label],
  );
  if (!result)
    return (
      <Unavailable
        title="Run result not found"
        detail="The record has no result with this id any more. Pick another for this widget."
      />
    );

  const { ref } = content;
  const drawItem = (item: WidgetSetItem): ReactNode => {
    if (item.kind === "preset") {
      const Widget = PRESET_WIDGETS[item.widgetId]?.component;
      return Widget ? (
        <Widget resultName={result.label} />
      ) : (
        <Unavailable title="Widget removed" detail="This built-in widget no longer exists." />
      );
    }
    if (item.kind === "custom")
      return (
        <CustomWidget
          item={item}
          onChange={noop}
          onDuplicate={noop}
          selectedRun={result}
          comparisonRun={null}
          startsEditing={false}
        />
      );
    return (
      <Unavailable
        title="Can't be placed"
        detail="Only charts, maps and tables go in a report. Use a text block for notes."
      />
    );
  };
  let widget: ReactNode;
  if (ref.source === "built-in") {
    const Widget = PRESET_WIDGETS[ref.widgetId]?.component;
    widget = Widget ? (
      <Widget resultName={result.label} />
    ) : (
      <Unavailable title="Widget removed" detail="This built-in widget no longer exists." />
    );
  } else if (ref.source === "detached") {
    widget = drawItem(ref.item);
  } else {
    const item = inspections
      .find((inspection) => inspection.id === ref.inspectionId)
      ?.items.find((candidate) => candidate.id === ref.itemId);
    widget = item ? (
      drawItem(item)
    ) : (
      <Unavailable
        title="Widget removed"
        detail="It was deleted from its view. Detach a widget to keep it in the report after that."
      />
    );
  }

  return (
    <WidgetPresentationContext.Provider value={presentation}>
      <ResultContext.Provider value={result.id}>
        <ComparisonContext.Provider value={null}>
          <InspectFilterContext.Provider value={filterContext}>
            {widget}
          </InspectFilterContext.Provider>
        </ComparisonContext.Provider>
      </ResultContext.Provider>
    </WidgetPresentationContext.Provider>
  );
}
