import { useEffect, useState } from "react";
import { Tabs } from "@base-ui/react/tabs";
import { LuTrash2 } from "react-icons/lu";
import { useProjectStore } from "../../project/store/project-store";
import {
  chartPresetForKind,
  type ChartKind,
  type ReportWidget,
} from "../../project/data/report-widgets";
import { FormSelect } from "../../home/components/form-select";

const CHART_KIND_OPTIONS: { value: ChartKind; label: string }[] = [
  { value: "pie", label: "Pie" },
  { value: "line", label: "Line" },
  { value: "bar", label: "Bar" },
];

type TrendDirection = "none" | "up" | "down";

const fieldLabel = "text-[11px] font-medium text-surface-400";
const fieldInput =
  "h-8 rounded border border-surface-600 bg-surface-900 px-2 text-[13px] text-surface-50 outline-none focus:border-accent-500";

// Same segmented-tab shape as AddDataDialog's Upload/URL switch — reusing
// its exact classes, including the two Base UI Tabs fixes that matter:
// Tabs.Indicator never sets width/left itself (only exposes the
// --active-tab-* custom properties), and the selected tab is only exposed
// via aria-selected, not a data-selected attribute.
const TAB_LIST_CLASS = "relative isolate flex items-center gap-1 rounded-md bg-surface-900 p-1";
const TAB_CLASS =
  "relative z-10 flex-1 rounded px-3 py-1 text-center text-[12px] font-medium text-surface-300 outline-none transition-colors aria-selected:text-white";
const TAB_INDICATOR_CLASS =
  "absolute top-1 bottom-1 left-[var(--active-tab-left)] z-0 w-[var(--active-tab-width)] rounded bg-accent-600 transition-all duration-200";

export function WidgetConfigForm() {
  const editingWidgetId = useProjectStore((s) => s.editingWidgetId);
  const reports = useProjectStore((s) => s.reports);
  const selectedReportId = useProjectStore((s) => s.selectedReportId);
  const closeNewWidgetDrawer = useProjectStore((s) => s.closeNewWidgetDrawer);
  const addWidgetToReport = useProjectStore((s) => s.addWidgetToReport);
  const updateWidgetInReport = useProjectStore((s) => s.updateWidgetInReport);
  const removeWidgetFromReport = useProjectStore((s) => s.removeWidgetFromReport);

  const report = reports.find((r) => r.id === selectedReportId);
  const editingWidget = editingWidgetId
    ? report?.widgets.find((w) => w.id === editingWidgetId)
    : undefined;
  const isEditing = editingWidget !== undefined;

  const [widgetType, setWidgetType] = useState<"stat" | "chart">("stat");
  const [label, setLabel] = useState("New Stat");
  const [value, setValue] = useState("0");
  const [sublabel, setSublabel] = useState("description");
  const [trendDirection, setTrendDirection] = useState<TrendDirection>("none");
  const [trendValue, setTrendValue] = useState("1.0%");
  const [chartTitle, setChartTitle] = useState("New Chart");
  const [chartKind, setChartKind] = useState<ChartKind>("pie");

  // Reload the form's fields whenever the widget being edited changes (or
  // reset to blank defaults for a new one). editingWidget's reference only
  // changes when the drawer targets a different widget or a save commits —
  // not on every keystroke, since the fields below are local state until
  // Save is clicked — so this doesn't fight the user's typing.
  useEffect(() => {
    if (editingWidget) {
      if (editingWidget.widgetType === "stat") {
        setWidgetType("stat");
        setLabel(editingWidget.label);
        setValue(editingWidget.value);
        setSublabel(editingWidget.sublabel);
        setTrendDirection(editingWidget.trend?.direction ?? "none");
        setTrendValue(editingWidget.trend?.value ?? "1.0%");
      } else {
        setWidgetType("chart");
        setChartTitle(editingWidget.title);
        setChartKind(editingWidget.kind);
      }
    } else {
      setWidgetType("stat");
      setLabel("New Stat");
      setValue("0");
      setSublabel("description");
      setTrendDirection("none");
      setTrendValue("1.0%");
      setChartTitle("New Chart");
      setChartKind("pie");
    }
  }, [editingWidget]);

  const buildWidget = (): ReportWidget => {
    const id = editingWidget?.id ?? `widget-${Date.now()}`;
    if (widgetType === "stat") {
      return {
        id,
        widgetType: "stat",
        label: label.trim() || "Untitled Stat",
        value: value.trim(),
        sublabel: sublabel.trim(),
        trend:
          trendDirection === "none"
            ? undefined
            : { direction: trendDirection, value: trendValue.trim() },
      };
    }
    // Keep an existing chart's own data when only its title changes; a new
    // chart, or a changed chart type, takes that type's sample dataset.
    const base =
      editingWidget?.widgetType === "chart" && editingWidget.kind === chartKind
        ? editingWidget
        : chartPresetForKind(chartKind);
    return { ...base, id, title: chartTitle.trim() || "Untitled Chart" };
  };

  const save = () => {
    if (!report) return;
    const widget = buildWidget();
    if (isEditing) {
      updateWidgetInReport(widget);
    } else {
      addWidgetToReport(widget);
    }
    closeNewWidgetDrawer();
  };

  const remove = () => {
    if (editingWidget) removeWidgetFromReport(editingWidget.id);
    closeNewWidgetDrawer();
  };

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
      <label className="flex flex-col gap-1">
        <span className={fieldLabel}>Widget Type</span>
        {isEditing ? (
          <div className="border-surface-600 bg-surface-900 text-surface-300 h-8 rounded border px-2 text-[13px] leading-8">
            {widgetType === "stat" ? "Stat" : "Chart"}
          </div>
        ) : (
          <Tabs.Root
            value={widgetType}
            onValueChange={(newValue) => setWidgetType(newValue as "stat" | "chart")}
          >
            <Tabs.List className={TAB_LIST_CLASS}>
              <Tabs.Tab value="stat" className={TAB_CLASS}>
                Stat
              </Tabs.Tab>
              <Tabs.Tab value="chart" className={TAB_CLASS}>
                Chart
              </Tabs.Tab>
              <Tabs.Indicator className={TAB_INDICATOR_CLASS} />
            </Tabs.List>
          </Tabs.Root>
        )}
      </label>

      {widgetType === "stat" ? (
        <>
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>Label</span>
            <input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              className={fieldInput}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>Value</span>
            <input
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className={fieldInput}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>Sublabel</span>
            <input
              value={sublabel}
              onChange={(event) => setSublabel(event.target.value)}
              className={fieldInput}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>Trend</span>
            <FormSelect
              value={trendDirection}
              onValueChange={(next) => setTrendDirection(next as TrendDirection)}
              options={[
                { value: "none", label: "None" },
                { value: "up", label: "Up" },
                { value: "down", label: "Down" },
              ]}
            />
          </label>
          {trendDirection !== "none" && (
            <label className="flex flex-col gap-1">
              <span className={fieldLabel}>Trend Value</span>
              <input
                value={trendValue}
                onChange={(event) => setTrendValue(event.target.value)}
                className={fieldInput}
              />
            </label>
          )}
        </>
      ) : (
        <>
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>Title</span>
            <input
              value={chartTitle}
              onChange={(event) => setChartTitle(event.target.value)}
              className={fieldInput}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>Chart Type</span>
            <FormSelect
              value={chartKind}
              onValueChange={(next) => setChartKind(next as ChartKind)}
              options={CHART_KIND_OPTIONS}
            />
          </label>
          <div className="border-surface-600 bg-surface-900 rounded border p-2">
            <div className="text-surface-400 text-[11px] font-medium">Data Source</div>
            <div className="text-surface-100 mt-1 text-[12px]">Sample dataset</div>
            <div className="text-surface-500 mt-1 text-[11px]">
              No run output wired up yet — uses sample data matching the chart type.
            </div>
          </div>
        </>
      )}

      <div className="border-surface-600/60 mt-auto flex flex-col gap-2 border-t pt-3">
        {isEditing && (
          <button
            onClick={remove}
            className="border-danger-500/50 text-danger-400 hover:bg-danger-500/10 flex items-center justify-center gap-1.5 rounded border px-3 py-1.5 text-[12px] font-medium outline-none"
          >
            <LuTrash2 size={13} />
            Delete Widget
          </button>
        )}
        <button
          onClick={save}
          disabled={!report}
          className="bg-accent-600 hover:bg-accent-500 rounded px-3 py-1.5 text-[12px] font-medium text-white outline-none disabled:pointer-events-none disabled:opacity-50"
        >
          {isEditing ? "Save Changes" : "Add Widget"}
        </button>
      </div>
    </div>
  );
}
