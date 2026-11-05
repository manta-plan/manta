import { useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "wouter";
import { HiOutlineDocumentMagnifyingGlass } from "react-icons/hi2";
import { LuLayoutDashboard, LuPencilLine, LuTrash2 } from "react-icons/lu";
import { BUILT_IN_INSPECTIONS } from "../../project/data/inspections";
import { projectInspectHref } from "../../project/lib/project-route";
import { useProjectStore } from "../../project/store/project-store";
import { ConfirmDialog } from "../../home/components/confirm-dialog";

function GroupLabel({ children }: { children: string }) {
  return (
    <div className="text-surface-500 px-3 pt-2.5 pb-1 text-[10px] font-medium tracking-wide uppercase">
      {children}
    </div>
  );
}

function InspectionRow({
  id,
  name,
  description,
  icon,
  tourId,
  actions,
}: {
  id: string;
  name: string;
  description: string;
  icon: "own" | "built-in";
  tourId?: string;
  actions?: ReactNode;
}) {
  const { projectId } = useParams<{ projectId: string }>();
  const selectedInspectionId = useProjectStore((s) => s.selectedInspectionId);
  const selectInspection = useProjectStore((s) => s.selectInspection);
  const isSelected = id === selectedInspectionId;
  const Icon = icon === "own" ? HiOutlineDocumentMagnifyingGlass : LuLayoutDashboard;

  return (
    <div className="group relative">
      <Link
        data-tour={tourId}
        href={projectInspectHref(projectId, isSelected ? undefined : id)}
        onClick={() => selectInspection(isSelected ? null : id)}
        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] outline-none ${actions ? "group-focus-within:pr-14 group-hover:pr-14" : ""} ${
          isSelected ? "bg-accent-600/25" : "hover:bg-surface-700/60"
        }`}
      >
        <Icon
          size={icon === "own" ? 15 : 14}
          className={`shrink-0 ${isSelected ? "text-accent-400" : "text-surface-400"}`}
        />
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span
            className={`text-surface-50 truncate font-medium ${description ? "max-w-[60%] shrink-0" : ""}`}
          >
            {name}
          </span>
          {description && (
            <>
              <span aria-hidden className="bg-surface-600 h-3 w-px shrink-0" />
              <span title={description} className="text-surface-400 min-w-0 truncate text-[11px]">
                {description}
              </span>
            </>
          )}
        </div>
      </Link>
      {actions && (
        <div className="absolute top-1/2 right-2 flex -translate-y-1/2 items-center gap-0.5">
          {actions}
        </div>
      )}
    </div>
  );
}

// The built-in inspections every project has, then the user's own.
export function InspectionsPanel() {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const selectedInspectionId = useProjectStore((s) => s.selectedInspectionId);
  const inspections = useProjectStore((s) => s.inspections);
  const openEditInspectionDrawer = useProjectStore((s) => s.openEditInspectionDrawer);
  const deleteInspection = useProjectStore((s) => s.deleteInspection);
  const [inspectionToDelete, setInspectionToDelete] = useState<{ id: string; name: string } | null>(
    null,
  );

  const confirmDeleteInspection = () => {
    if (!inspectionToDelete) return;
    // Leave the deleted inspection's detail route so the workspace doesn't point at a missing inspection.
    if (selectedInspectionId === inspectionToDelete.id) navigate(projectInspectHref(projectId));
    deleteInspection(inspectionToDelete.id);
    setInspectionToDelete(null);
  };

  return (
    <div className="h-full overflow-y-auto pb-1">
      <GroupLabel>Built-in</GroupLabel>
      {BUILT_IN_INSPECTIONS.map((inspection, index) => (
        <InspectionRow
          key={inspection.id}
          id={inspection.id}
          name={inspection.name}
          description={inspection.description}
          icon="built-in"
          tourId={index === 0 ? "inspection-item" : undefined}
        />
      ))}

      <GroupLabel>Yours</GroupLabel>
      {inspections.map((inspection) => (
        <InspectionRow
          key={inspection.id}
          id={inspection.id}
          name={inspection.name}
          description={inspection.description}
          icon="own"
          actions={
            <>
              <button
                type="button"
                aria-label={`Edit ${inspection.name}`}
                title="Edit inspection"
                onClick={() => openEditInspectionDrawer(inspection.id)}
                className="text-surface-400 hover:bg-surface-600 hover:text-surface-50 flex h-6 w-6 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100"
              >
                <LuPencilLine size={13} />
              </button>
              <button
                type="button"
                aria-label={`Delete ${inspection.name}`}
                title="Delete inspection"
                onClick={() => setInspectionToDelete({ id: inspection.id, name: inspection.name })}
                className="text-surface-400 hover:bg-surface-600 hover:text-danger-400 flex h-6 w-6 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100"
              >
                <LuTrash2 size={13} />
              </button>
            </>
          }
        />
      ))}
      {inspections.length === 0 && (
        <div className="text-surface-400 px-3 py-2 text-[12px] leading-5">
          None yet. Create one, or open a built-in inspection and save it as your own.
        </div>
      )}

      <ConfirmDialog
        open={Boolean(inspectionToDelete)}
        onOpenChange={(open) => !open && setInspectionToDelete(null)}
        title="Delete Inspection"
        description={
          inspectionToDelete
            ? `Delete ${inspectionToDelete.name}? Its widgets, result, comparison and filters are removed.`
            : ""
        }
        onConfirm={confirmDeleteInspection}
        confirmLabel="Delete"
      />
    </div>
  );
}
