import { useEffect } from "react";
import { useLocation } from "wouter";
import { LuListFilter, LuX } from "react-icons/lu";
import { getActiveProjectTab, type ProjectTab } from "../../project/lib/project-route";
import { useProjectStore } from "../../project/store/project-store";

interface FilterDrawerProps {
  activeTab: ProjectTab;
  title: string;
  options: string[];
  isOpen: boolean;
  selected: string[];
  onClose: () => void;
  onToggle: (option: string) => void;
  onClear: () => void;
}

function WorkspaceFilterDrawer({
  activeTab,
  title,
  options,
  isOpen,
  selected,
  onClose,
  onToggle,
  onClear,
}: FilterDrawerProps) {
  const [location] = useLocation();

  useEffect(() => {
    if (getActiveProjectTab(location) !== activeTab) onClose();
  }, [activeTab, location, onClose]);

  return (
    <aside
      className={`border-surface-600/60 bg-surface-800/70 absolute top-0 left-0 z-20 flex h-full w-72 flex-col border-r backdrop-blur-xl transition-transform duration-200 ease-out ${isOpen ? "pointer-events-auto translate-x-0" : "pointer-events-none -translate-x-full"}`}
    >
      <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
        <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          <LuListFilter size={12} />
          {title}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={`Close ${title.toLowerCase()}`}
          className="text-surface-400 hover:text-surface-100 outline-none"
        >
          <LuX size={14} />
        </button>
      </div>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-3">
        <span className="text-surface-400 text-[11px] font-medium">Filters</span>
        {options.map((option) => (
          <label
            key={option}
            className="text-surface-200 hover:bg-surface-700 flex h-8 cursor-pointer items-center gap-2 rounded px-2 text-[12px]"
          >
            <input
              type="checkbox"
              checked={selected.includes(option)}
              onChange={() => onToggle(option)}
              className="accent-accent-500 h-3.5 w-3.5"
            />
            {option}
          </label>
        ))}
      </div>
      <div className="border-surface-600/60 shrink-0 border-t p-3">
        <button
          type="button"
          onClick={onClear}
          disabled={selected.length === 0}
          className="border-surface-600 text-surface-200 hover:bg-surface-700 w-full rounded border px-3 py-1.5 text-[12px] font-medium outline-none disabled:cursor-not-allowed disabled:opacity-45"
        >
          Clear Filters
        </button>
      </div>
    </aside>
  );
}

export function InspectionFilterDrawer() {
  const isOpen = useProjectStore((s) => s.isInspectionFilterDrawerOpen);
  const selected = useProjectStore((s) => s.inspectionFilters);
  const onClose = useProjectStore((s) => s.closeInspectionFilterDrawer);
  const onToggle = useProjectStore((s) => s.toggleInspectionFilter);
  const onClear = useProjectStore((s) => s.clearInspectionFilters);
  return (
    <WorkspaceFilterDrawer
      activeTab="inspect"
      title="Inspection Filters"
      options={["With run result", "Comparison", "Constraint review"]}
      isOpen={isOpen}
      selected={selected}
      onClose={onClose}
      onToggle={onToggle}
      onClear={onClear}
    />
  );
}

export function ReportFilterDrawer() {
  const isOpen = useProjectStore((s) => s.isReportFilterDrawerOpen);
  const selected = useProjectStore((s) => s.reportFilters);
  const onClose = useProjectStore((s) => s.closeReportFilterDrawer);
  const onToggle = useProjectStore((s) => s.toggleReportFilter);
  const onClear = useProjectStore((s) => s.clearReportFilters);
  return (
    <WorkspaceFilterDrawer
      activeTab="report"
      title="Report Filters"
      options={["Blank", "With charts", "Output summary"]}
      isOpen={isOpen}
      selected={selected}
      onClose={onClose}
      onToggle={onToggle}
      onClear={onClear}
    />
  );
}
