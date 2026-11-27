// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "wouter";
import { HiOutlineDocumentMagnifyingGlass } from "react-icons/hi2";
import { LuLayoutDashboard, LuPencilLine, LuTrash2 } from "react-icons/lu";
import { BUILT_IN_INSPECTIONS } from "../data/inspections";
import { projectAnalyseHref } from "../../project/lib/project-route";
import { useProjectStore } from "../../project/store/project-store";
import { ConfirmDialog } from "../../../components/confirm-dialog";
import { RecordSearchBox } from "../../level/tree/record-search";

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
  const selectedViewId = useProjectStore((s) => s.selectedViewId);
  const selectView = useProjectStore((s) => s.selectView);
  const isSelected = id === selectedViewId;
  const Icon = icon === "own" ? HiOutlineDocumentMagnifyingGlass : LuLayoutDashboard;

  return (
    <div className="group relative">
      <Link
        data-tour={tourId}
        href={projectAnalyseHref(projectId, isSelected ? undefined : id)}
        onClick={() => selectView(isSelected ? null : id)}
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

// Whether a view matches the find box: every word, in its name or description.
function matches(view: { name: string; description: string }, term: string) {
  const text = `${view.name} ${view.description}`.toLowerCase();
  return term
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => text.includes(word));
}

// The built-in inspections every project has, then the user's own, with a
// find box over both.
export function InspectionsPanel({ showSearch }: { showSearch: boolean }) {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const selectedViewId = useProjectStore((s) => s.selectedViewId);
  const inspections = useProjectStore((s) => s.inspections);
  const openEditInspectionDrawer = useProjectStore((s) => s.openEditInspectionDrawer);
  const deleteInspection = useProjectStore((s) => s.deleteInspection);
  const [inspectionToDelete, setInspectionToDelete] = useState<{ id: string; name: string } | null>(
    null,
  );
  const [term, setFind] = useState("");
  // A hidden find box finds nothing.
  const find = showSearch ? term : "";
  const isFinding = find.trim() !== "";
  const builtIns = BUILT_IN_INSPECTIONS.filter((view) => matches(view, find));
  const own = inspections.filter((view) => matches(view, find));

  const confirmDeleteInspection = () => {
    if (!inspectionToDelete) return;
    // Leave the deleted inspection's detail route so the workspace doesn't point at a missing inspection.
    if (selectedViewId === inspectionToDelete.id) navigate(projectAnalyseHref(projectId));
    deleteInspection(inspectionToDelete.id);
    setInspectionToDelete(null);
  };

  return (
    <div className="flex h-full flex-col">
      {showSearch && (
        <RecordSearchBox term={term} onChange={setFind} placeholder="Find a view" autoFocus />
      )}
      <div className="min-h-0 flex-1 overflow-y-auto pb-1">
        {builtIns.length > 0 && <GroupLabel>Built-in</GroupLabel>}
        {builtIns.map((inspection, index) => (
          <InspectionRow
            key={inspection.id}
            id={inspection.id}
            name={inspection.name}
            description={inspection.description}
            icon="built-in"
            tourId={index === 0 ? "inspection-item" : undefined}
          />
        ))}

        {(!isFinding || own.length > 0) && <GroupLabel>Yours</GroupLabel>}
        {own.map((inspection) => (
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
                  title="Edit view"
                  onClick={() => openEditInspectionDrawer(inspection.id)}
                  className="text-surface-400 hover:bg-surface-600 hover:text-surface-50 flex h-6 w-6 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <LuPencilLine size={13} />
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${inspection.name}`}
                  title="Delete view"
                  onClick={() =>
                    setInspectionToDelete({ id: inspection.id, name: inspection.name })
                  }
                  className="text-surface-400 hover:bg-surface-600 hover:text-danger-400 flex h-6 w-6 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <LuTrash2 size={13} />
                </button>
              </>
            }
          />
        ))}
        {isFinding && builtIns.length === 0 && own.length === 0 && (
          <div className="text-surface-400 px-3 py-2 text-[12px] leading-5">
            No views match “{find.trim()}”.
          </div>
        )}
        {!isFinding && inspections.length === 0 && (
          <div className="text-surface-400 px-3 py-2 text-[12px] leading-5">
            None yet. Create one, or open a built-in view and save it as your own.
          </div>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(inspectionToDelete)}
        onOpenChange={(open) => !open && setInspectionToDelete(null)}
        title="Delete View"
        description={
          inspectionToDelete
            ? `Delete ${inspectionToDelete.name}? Its widgets and filters are removed.`
            : ""
        }
        onConfirm={confirmDeleteInspection}
        confirmLabel="Delete"
      />
    </div>
  );
}
