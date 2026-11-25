import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useParams } from "wouter";
import clsx from "clsx";
import { LuChartBar, LuFilePlus, LuPencilLine, LuX } from "react-icons/lu";
import { PAPER_SIZES, type PaperOrientation, type PaperSize } from "../data/reports";
import { presetTheme, REPORT_THEME_PRESETS } from "../data/report-themes";
import { buildTemplatePages, REPORT_TEMPLATES, reportTemplate } from "../data/report-templates";
import { recordResults } from "../../project/lib/record-results";
import { ReportTemplatePreview } from "./report-template-preview";
import { useProjectStore } from "../../project/store/project-store";
import { FormSelect } from "../../../components/form-select";
import { getActiveProjectTab, projectAnalyseHref } from "../../project/lib/project-route";

const SIZE_OPTIONS = (Object.keys(PAPER_SIZES) as PaperSize[]).map((size) => ({
  value: size,
  label: PAPER_SIZES[size].label,
}));
const THEME_OPTIONS = REPORT_THEME_PRESETS.map((preset) => ({
  value: preset.id,
  label: preset.name,
}));
const ORIENTATIONS: { value: PaperOrientation; label: string }[] = [
  { value: "portrait", label: "Portrait" },
  { value: "landscape", label: "Landscape" },
];

export function NewReportDrawer() {
  const [location, setLocation] = useLocation();
  const { projectId } = useParams<{ projectId: string }>();
  const activeTab = getActiveProjectTab(location);
  const isOpen = useProjectStore((s) => s.isNewReportDrawerOpen);
  const closeNewReportDrawer = useProjectStore((s) => s.closeNewReportDrawer);
  const createReport = useProjectStore((s) => s.createReport);
  const updateReport = useProjectStore((s) => s.updateReport);
  const editingReportId = useProjectStore((s) => s.editingReportId);
  const editingReport = useProjectStore((s) =>
    s.editingReportId ? (s.reports.find((r) => r.id === s.editingReportId) ?? null) : null,
  );
  const isEditing = editingReport !== null;

  const [name, setName] = useState("");
  const [size, setSize] = useState<PaperSize>("a4");
  const [orientation, setOrientation] = useState<PaperOrientation>("portrait");
  const [themeId, setThemeId] = useState("paper");
  const [templateId, setTemplateId] = useState("blank");
  // The record's run results, to fill a template's widgets. They aren't there while the record is still opening.
  const record = useProjectStore((s) => s.record);
  const results = useMemo(() => (record ? recordResults(record.info) : []), [record]);
  // A comparison is most telling between two kinds of run (perfect vs myopic), not a run and its patched twin.
  const runKind = (id: string) => id.split("/").pop() ?? id;
  const second =
    results.find((result) => runKind(result.id) !== runKind(results[0]?.id ?? "")) ??
    results[1] ??
    results[0];
  const resultPair: [{ id: string; label: string }, { id: string; label: string }] | null =
    results.length > 0 ? [results[0], second] : null;
  const template = reportTemplate(templateId);
  const setup = { size, orientation };
  const previews = useMemo(
    () =>
      Object.fromEntries(
        REPORT_TEMPLATES.map((option) => [
          option.id,
          buildTemplatePages(
            option,
            { size, orientation },
            {
              name: "Report title",
              results: resultPair ?? [
                { id: "", label: "Result A" },
                { id: "", label: "Result B" },
              ],
            },
          )[0],
        ]),
      ),
    // resultPair is rebuilt each render; the results themselves are what it follows.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [size, orientation, results],
  );

  useEffect(() => {
    if (activeTab !== "analyse") closeNewReportDrawer();
  }, [activeTab, closeNewReportDrawer]);

  const nameInput = useRef<HTMLInputElement>(null);

  // Seeds once per open.
  useEffect(() => {
    if (!isOpen) return;
    // The closed drawer is inert, so focus moves in once it is open.
    requestAnimationFrame(() => nameInput.current?.focus());
    setName(editingReport?.name ?? "");
    setSize(editingReport?.page.size ?? "a4");
    setOrientation(editingReport?.page.orientation ?? "portrait");
    setThemeId("paper");
    setTemplateId("blank");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, editingReportId]);

  const submit = () => {
    const page = { size, orientation };
    if (editingReport) {
      updateReport(editingReport.id, { name, page });
      return;
    }
    const pages =
      resultPair || !template.needsResults
        ? buildTemplatePages(template, page, {
            name: name.trim(),
            results: resultPair ?? [
              { id: "", label: "" },
              { id: "", label: "" },
            ],
          })
        : undefined;
    const report = createReport({ name, page, theme: presetTheme(themeId), pages });
    setLocation(projectAnalyseHref(projectId, report.id));
  };

  return (
    <aside
      inert={!isOpen}
      aria-hidden={!isOpen}
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
            ref={nameInput}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Winter adequacy summary"
            className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 h-8 rounded border px-2 text-[13px] outline-none"
          />
        </label>

        {/* An existing report's layout is its own; a template only starts a new one. */}
        {!isEditing && (
          <div role="radiogroup" aria-label="Template" className="flex flex-col gap-1">
            <span className="text-surface-400 text-[11px] font-medium">Template</span>
            <div className="grid grid-cols-2 gap-1.5">
              {REPORT_TEMPLATES.map((option) => {
                const isUnavailable = option.needsResults && !resultPair;
                const isSelected = option.id === templateId;
                const preview = previews[option.id];
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    disabled={isUnavailable}
                    onClick={() => setTemplateId(option.id)}
                    title={
                      isUnavailable
                        ? "Available once the project's record has opened"
                        : option.description
                    }
                    className={clsx(
                      "flex flex-col items-center gap-1.5 rounded border p-2 text-center outline-none disabled:cursor-not-allowed disabled:opacity-40",
                      isSelected
                        ? "border-accent-500 bg-accent-600/15"
                        : "border-surface-600 bg-surface-900 hover:border-surface-500",
                    )}
                  >
                    {/* A fixed slot, so switching paper or orientation doesn't move the form under the pointer. */}
                    <div className="flex h-16 w-16 shrink-0 items-center justify-center">
                      <ReportTemplatePreview
                        blocks={preview.blocks}
                        setup={setup}
                        widthPx={orientation === "portrait" ? 44 : 64}
                      />
                    </div>
                    <span className="text-surface-100 text-[11px] leading-4 font-medium">
                      {option.name}
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="text-surface-500 min-h-8 text-[11px] leading-4">
              {resultPair || !template.needsResults
                ? template.description
                : "Templates with charts need the project's record to have opened."}
            </p>
          </div>
        )}

        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px] font-medium">Paper Size</span>
          <FormSelect
            value={size}
            onValueChange={(value) => setSize(value as PaperSize)}
            placeholder="Select paper size"
            options={SIZE_OPTIONS}
          />
        </label>

        {/* An existing report's theme is changed in its Theme tab, where its edits are kept. */}
        {!isEditing && (
          <label className="flex flex-col gap-1">
            <span className="text-surface-400 text-[11px] font-medium">Theme</span>
            <FormSelect
              value={themeId}
              onValueChange={setThemeId}
              placeholder="Select theme"
              options={THEME_OPTIONS}
            />
          </label>
        )}

        <div role="radiogroup" aria-label="Orientation" className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px] font-medium">Orientation</span>
          <div className="grid grid-cols-2 gap-2">
            {ORIENTATIONS.map((option) => {
              const isSelected = option.value === orientation;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  onClick={() => setOrientation(option.value)}
                  className={clsx(
                    "flex h-9 items-center justify-center gap-2 rounded border text-[12px] font-medium outline-none",
                    isSelected
                      ? "border-accent-500 bg-accent-600/15 text-surface-50"
                      : "border-surface-600 bg-surface-900 text-surface-300 hover:border-surface-500 hover:text-surface-100",
                  )}
                >
                  <span
                    aria-hidden
                    className={clsx(
                      "border border-current",
                      option.value === "portrait" ? "h-3.5 w-2.5" : "h-2.5 w-3.5",
                    )}
                  />
                  {option.label}
                </button>
              );
            })}
          </div>
          {isEditing && (
            <p className="text-surface-500 text-[11px] leading-4">
              Changing the paper rescales the layout to the new page. A block that no longer fits
              moves to a new page.
            </p>
          )}
        </div>
      </div>

      <div className="border-surface-600/60 flex shrink-0 justify-end gap-2 border-t p-3">
        <button
          onClick={closeNewReportDrawer}
          className="border-surface-600 text-surface-300 hover:bg-surface-700 rounded border px-3 py-1.5 text-[12px] font-medium outline-none"
        >
          Cancel
        </button>
        <button
          onClick={submit}
          disabled={name.trim().length === 0}
          className="bg-accent-600 hover:bg-accent-500 flex items-center gap-1.5 rounded px-3 py-1.5 text-[12px] font-medium text-white outline-none disabled:pointer-events-none disabled:opacity-50"
        >
          {isEditing ? null : <LuFilePlus size={13} />}
          {isEditing ? "Save" : "Create Report"}
        </button>
      </div>
    </aside>
  );
}
