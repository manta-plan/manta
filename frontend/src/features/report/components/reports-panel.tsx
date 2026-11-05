import { useState } from "react";
import { LuFileText, LuPencilLine, LuTrash2 } from "react-icons/lu";
import { Link, useLocation, useParams } from "wouter";
import { useProjectStore } from "../../project/store/project-store";
import { projectReportHref } from "../../project/lib/project-route";
import { ConfirmDialog } from "../../home/components/confirm-dialog";

export function ReportsPanel() {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const reports = useProjectStore((s) => s.reports);
  const selectedReportId = useProjectStore((s) => s.selectedReportId);
  const selectReport = useProjectStore((s) => s.selectReport);
  const isReportTourPlaceholderVisible = useProjectStore((s) => s.isReportTourPlaceholderVisible);
  const showTourPlaceholder = reports.length === 0 && isReportTourPlaceholderVisible;
  const openEditReportDrawer = useProjectStore((s) => s.openEditReportDrawer);
  const deleteReport = useProjectStore((s) => s.deleteReport);
  const [reportToDelete, setReportToDelete] = useState<{ id: string; name: string } | null>(null);

  const confirmDeleteReport = () => {
    if (!reportToDelete) return;
    // Leave the deleted report's detail route so the workspace doesn't point at a missing report.
    if (selectedReportId === reportToDelete.id) navigate(projectReportHref(projectId));
    deleteReport(reportToDelete.id);
    setReportToDelete(null);
  };

  return (
    <div className="h-full overflow-y-auto py-1">
      {showTourPlaceholder && (
        // Non-interactive stand-in so the Report tour has something to point
        // at when the project has no reports yet — toggled by
        // startReportWorkspaceTour, not part of the real list.
        <div
          data-tour="report-item"
          className="flex cursor-default items-center gap-2 px-3 py-1.5 text-[12px] opacity-60"
        >
          <LuFileText size={14} className="text-accent-400 shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="text-surface-50 truncate font-medium">Example report</div>
            <div className="text-surface-400 truncate text-[11px]">
              Appears here once you create one
            </div>
          </div>
        </div>
      )}
      {reports.map((report, index) => {
        const isSelected = selectedReportId === report.id;
        return (
          <div key={report.id} className="group relative">
            <Link
              data-tour={index === 0 ? "report-item" : undefined}
              href={projectReportHref(projectId, isSelected ? undefined : report.id)}
              onClick={() => selectReport(isSelected ? null : report.id)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-[12px] group-focus-within:pr-14 group-hover:pr-14 ${
                isSelected ? "bg-accent-600/25" : "hover:bg-surface-700/60"
              }`}
            >
              <LuFileText size={14} className="text-accent-400 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-surface-50 truncate font-medium">{report.name}</div>
                <div className="text-surface-400 truncate text-[11px]">{report.generatedAt}</div>
              </div>
            </Link>
            <div className="absolute top-1/2 right-2 flex -translate-y-1/2 items-center gap-0.5">
              <button
                type="button"
                aria-label={`Edit ${report.name}`}
                title="Edit report"
                onClick={() => openEditReportDrawer(report.id)}
                className="text-surface-400 hover:bg-surface-600 hover:text-surface-50 flex h-6 w-6 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100"
              >
                <LuPencilLine size={13} />
              </button>
              <button
                type="button"
                aria-label={`Delete ${report.name}`}
                title="Delete report"
                onClick={() => setReportToDelete({ id: report.id, name: report.name })}
                className="text-surface-400 hover:bg-surface-600 hover:text-danger-400 flex h-6 w-6 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100"
              >
                <LuTrash2 size={13} />
              </button>
            </div>
          </div>
        );
      })}
      {reports.length === 0 && !showTourPlaceholder && (
        <div className="text-surface-400 px-3 py-5 text-center text-[12px]">
          No reports yet — create one to get started.
        </div>
      )}
      <ConfirmDialog
        open={Boolean(reportToDelete)}
        onOpenChange={(open) => !open && setReportToDelete(null)}
        title="Delete Report"
        description={
          reportToDelete
            ? `Delete ${reportToDelete.name}? Its dashboard and widgets will be removed; the run it reports on is kept.`
            : ""
        }
        onConfirm={confirmDeleteReport}
        confirmLabel="Delete"
      />
    </div>
  );
}
