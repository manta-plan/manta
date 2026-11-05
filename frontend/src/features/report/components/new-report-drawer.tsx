import { useEffect, useState } from "react";
import { useLocation, useParams } from "wouter";
import clsx from "clsx";
import { LuChartBar, LuFilePlus, LuFileText, LuPencilLine, LuWorkflow, LuX } from "react-icons/lu";
import type { IconType } from "react-icons";
import type { ReportCanvasPreset } from "../../project/data/reports";
import { DUMMY_RESULT_RUNS, runLabel } from "../../project/data/inspect-results";
import { useProjectStore } from "../../project/store/project-store";
import { FormSelect } from "../../home/components/form-select";
import { getActiveProjectTab, projectReportHref } from "../../project/lib/project-route";

const CANVAS_PRESETS: {
  id: ReportCanvasPreset;
  label: string;
  description: string;
  icon: IconType;
}[] = [
  {
    id: "blank",
    label: "Start blank",
    description: "Build the report from scratch.",
    icon: LuFileText,
  },
  {
    id: "playbook-hint",
    label: "Use playbook hint",
    description: "Start with workflow-oriented charts.",
    icon: LuWorkflow,
  },
  {
    id: "output-summary",
    label: "Use output summary",
    description: "Start with key run result metrics.",
    icon: LuChartBar,
  },
];

export function NewReportDrawer() {
  const [location, setLocation] = useLocation();
  const { projectId } = useParams<{ projectId: string }>();
  const activeTab = getActiveProjectTab(location);
  const isOpen = useProjectStore((s) => s.isNewReportDrawerOpen);
  const closeNewReportDrawer = useProjectStore((s) => s.closeNewReportDrawer);
  const createReport = useProjectStore((s) => s.createReport);
  const renameReport = useProjectStore((s) => s.renameReport);
  const editingReportId = useProjectStore((s) => s.editingReportId);
  const editingReport = useProjectStore((s) =>
    s.editingReportId ? (s.reports.find((r) => r.id === s.editingReportId) ?? null) : null,
  );
  const isEditing = editingReport !== null;
  const newReportResultId = useProjectStore((s) => s.newReportResultId);

  // Fully dummy for the demo, like Inspect: reports pick from these results
  // instead of the project's runs.
  const results = DUMMY_RESULT_RUNS;
  const resultOptions = results.map((run) => ({ value: run.id, label: runLabel(run) }));

  const [runId, setRunId] = useState("");
  // null until the user types, so the name keeps following the chosen output.
  const [reportNameDraft, setReportNameDraft] = useState<string | null>(null);
  const [canvasPreset, setCanvasPreset] = useState<ReportCanvasPreset>("blank");
  const result = results.find((run) => run.id === runId) ?? null;
  const reportName = reportNameDraft ?? (result ? `${result.scenarioName} — System Overview` : "");

  useEffect(() => {
    if (activeTab !== "report") closeNewReportDrawer();
  }, [activeTab, closeNewReportDrawer]);

  // Seeds once per open. Clicking a result in the Run Results panel opens
  // this drawer with that result as the prefill; otherwise the first one.
  useEffect(() => {
    if (!isOpen) return;
    if (editingReport) {
      setRunId(editingReport.runId ?? "");
      setReportNameDraft(editingReport.name);
      return;
    }
    setRunId(results.find((run) => run.id === newReportResultId)?.id ?? results[0].id);
    setReportNameDraft(null);
    setCanvasPreset("blank");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, newReportResultId, editingReportId]);

  const createReportFromPreset = () => {
    if (editingReport) {
      renameReport(editingReport.id, reportName);
      return;
    }
    if (!result) return;
    const report = createReport({
      name: reportName,
      scenarioName: result.scenarioName,
      runId: result.id,
      canvasPreset,
    });
    setLocation(projectReportHref(projectId, report.id));
  };

  return (
    <aside
      className={clsx(
        "absolute top-0 left-0 z-20 flex h-full w-72 flex-col border-r border-surface-600/60 bg-surface-800/70 backdrop-blur-xl transition-transform duration-200 ease-out",
        isOpen ? "translate-x-0 pointer-events-auto" : "-translate-x-full pointer-events-none",
      )}
    >
      <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
        <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          {isEditing ? <LuPencilLine size={12} /> : <LuChartBar size={12} />}
          {isEditing ? "Edit Report" : "New Report"}
        </div>
        <button
          onClick={closeNewReportDrawer}
          className="text-surface-400 hover:text-surface-100 outline-none"
        >
          <LuX size={14} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px] font-medium">Report Name</span>
          <input
            value={reportName}
            onChange={(event) => setReportNameDraft(event.target.value)}
            className="border-surface-600 bg-surface-900 text-surface-50 focus:border-accent-500 h-8 rounded border px-2 text-[13px] outline-none"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px] font-medium">Run Result</span>
          <FormSelect
            value={runId || null}
            onValueChange={setRunId}
            placeholder="Select run result"
            options={resultOptions}
            disabled={isEditing}
          />
          {isEditing && (
            <span className="text-surface-500 text-[11px]">
              A report stays tied to the output it was created for.
            </span>
          )}
        </label>

        {/* Presets only seed a new report's starting widgets; an existing
            report's dashboard is edited through its widgets instead. */}
        {!isEditing && (
          <div className="flex flex-col gap-1.5">
            <div className="text-surface-400 text-[11px] font-medium">Canvas</div>
            {CANVAS_PRESETS.map((preset) => {
              const Icon = preset.icon;
              const isSelected = preset.id === canvasPreset;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => setCanvasPreset(preset.id)}
                  className={`flex items-start gap-2 border p-2 text-left outline-none ${isSelected ? "border-accent-500 bg-accent-600/15" : "border-surface-600 bg-surface-900 hover:bg-surface-800"}`}
                >
                  <Icon
                    size={15}
                    className={`mt-0.5 shrink-0 ${isSelected ? "text-accent-400" : "text-surface-400"}`}
                  />
                  <span className="min-w-0">
                    <span className="text-surface-100 block text-[12px] font-medium">
                      {preset.label}
                    </span>
                    <span className="text-surface-400 mt-0.5 block text-[11px] leading-4">
                      {preset.description}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="border-surface-600/60 flex shrink-0 justify-end gap-2 border-t p-3">
        <button
          onClick={closeNewReportDrawer}
          className="border-surface-600 text-surface-300 hover:bg-surface-700 rounded border px-3 py-1.5 text-[12px] font-medium outline-none"
        >
          Cancel
        </button>
        <button
          onClick={createReportFromPreset}
          disabled={(!isEditing && !result) || reportName.trim().length === 0}
          className="bg-accent-600 hover:bg-accent-500 flex items-center gap-1.5 rounded px-3 py-1.5 text-[12px] font-medium text-white outline-none disabled:pointer-events-none disabled:opacity-50"
        >
          {isEditing ? null : <LuFilePlus size={13} />}
          {isEditing ? "Save" : "Create Report"}
        </button>
      </div>
    </aside>
  );
}
