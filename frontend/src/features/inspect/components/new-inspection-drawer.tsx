import { useEffect, useState } from "react";
import { useLocation, useParams } from "wouter";
import clsx from "clsx";
import { Select } from "@base-ui/react/select";
import { LuCheck, LuChevronDown, LuFiles, LuPencilLine, LuPlus, LuX } from "react-icons/lu";
import {
  BUILT_IN_INSPECTIONS,
  builtInInspection,
  type InspectionCanvas,
  type InspectionContent,
} from "../../project/data/inspections";
import { blankCustomItem } from "../../project/lib/blank-inspection";
import { builtInItems, copyWidgetItem } from "../../project/lib/widget-sets";
import { projectInspectHref, getActiveProjectTab } from "../../project/lib/project-route";
import { useProjectStore } from "../../project/store/project-store";

const BLANK = "blank";

const selectItemClassName =
  "flex h-7 cursor-default items-center gap-2 rounded px-2 text-[12px] text-surface-200 outline-none data-[highlighted]:bg-surface-700 data-[selected]:text-surface-50";
const selectGroupLabelClassName =
  "px-2 pt-1.5 pb-1 text-[10px] font-medium uppercase tracking-wide text-surface-500";

// A blank page, a built-in inspection, or one of the user's own to copy.
function StartFromSelect({
  value,
  onValueChange,
  inspections,
}: {
  value: string;
  onValueChange: (value: string) => void;
  inspections: InspectionCanvas[];
}) {
  const builtIn = BUILT_IN_INSPECTIONS.map((inspection) => ({
    value: inspection.id,
    label: inspection.name,
  }));
  const own = inspections.map((inspection) => ({ value: inspection.id, label: inspection.name }));
  const renderItem = (item: { value: string; label: string }) => (
    <Select.Item key={item.value} value={item.value} className={selectItemClassName}>
      <Select.ItemText className="min-w-0 flex-1 truncate">{item.label}</Select.ItemText>
      <Select.ItemIndicator className="text-accent-400">
        <LuCheck size={13} />
      </Select.ItemIndicator>
    </Select.Item>
  );

  return (
    <Select.Root
      value={value}
      onValueChange={(nextValue) => nextValue && onValueChange(nextValue)}
      items={[{ value: BLANK, label: "Blank page" }, ...builtIn, ...own]}
    >
      <Select.Trigger className="border-surface-600 bg-surface-900 text-surface-50 focus-visible:border-accent-500 flex h-8 w-full items-center gap-2 rounded border px-2 text-left text-[13px] outline-none">
        <Select.Value className="min-w-0 flex-1 truncate" />
        <Select.Icon className="text-surface-400">
          <LuChevronDown size={13} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner sideOffset={4} className="z-50">
          <Select.Popup className="border-surface-600 bg-surface-800 max-h-80 min-w-[var(--anchor-width)] overflow-y-auto rounded border p-1 shadow-xl outline-none">
            <Select.List>
              {renderItem({ value: BLANK, label: "Blank page" })}
              <Select.Separator className="bg-surface-600 my-1 h-px" />
              <Select.Group>
                <Select.GroupLabel className={selectGroupLabelClassName}>
                  Built-in
                </Select.GroupLabel>
                {builtIn.map(renderItem)}
              </Select.Group>
              {own.length > 0 && (
                <>
                  <Select.Separator className="bg-surface-600 my-1 h-px" />
                  <Select.Group>
                    <Select.GroupLabel className={selectGroupLabelClassName}>
                      Yours
                    </Select.GroupLabel>
                    {own.map(renderItem)}
                  </Select.Group>
                </>
              )}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}

// What a new inspection's page starts with: a copy of the chosen one's
// widgets, plus the result, comparison and filters of one of the user's own.
function startingContent(startFrom: string, inspections: InspectionCanvas[]): InspectionContent {
  const builtIn = builtInInspection(startFrom);
  if (builtIn) return { items: builtInItems(builtIn.widgetIds) };
  const source = inspections.find((inspection) => inspection.id === startFrom);
  if (source)
    return {
      items: source.items.map(copyWidgetItem),
      resultId: source.resultId,
      comparisonResultId: source.comparisonResultId,
      filters: source.filters,
    };
  return { items: [blankCustomItem()] };
}

export function NewInspectionDrawer() {
  const [location, setLocation] = useLocation();
  const { projectId } = useParams<{ projectId: string }>();
  const isOpen = useProjectStore((s) => s.isNewInspectionDrawerOpen);
  const closeNewInspectionDrawer = useProjectStore((s) => s.closeNewInspectionDrawer);
  const createInspection = useProjectStore((s) => s.createInspection);
  const updateInspection = useProjectStore((s) => s.updateInspection);
  const editingInspectionId = useProjectStore((s) => s.editingInspectionId);
  const editingInspection = useProjectStore((s) =>
    s.editingInspectionId
      ? (s.inspections.find((i) => i.id === s.editingInspectionId) ?? null)
      : null,
  );
  const isEditing = editingInspection !== null;
  const inspections = useProjectStore((s) => s.inspections);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [startFrom, setStartFrom] = useState(BLANK);

  useEffect(() => {
    if (getActiveProjectTab(location) !== "inspect") closeNewInspectionDrawer();
  }, [closeNewInspectionDrawer, location]);

  // Seeds once per open (or per inspection being edited). `editingInspection`
  // is a fresh object every render, so it can't be a dependency — that would
  // re-run this on each keystroke and wipe the fields as the user types.
  useEffect(() => {
    if (!isOpen) return;
    setName(editingInspection?.name ?? "");
    setDescription(editingInspection?.description ?? "");
    setStartFrom(BLANK);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, editingInspectionId]);

  const submit = () => {
    if (!name.trim()) return;
    if (editingInspection) {
      updateInspection(editingInspection.id, { name, description });
      return;
    }
    const inspection = createInspection({
      name,
      description,
      ...startingContent(startFrom, inspections),
    });
    setLocation(projectInspectHref(projectId, inspection.id));
  };

  return (
    <aside
      className={clsx(
        "absolute top-0 left-0 z-20 flex h-full w-72 flex-col border-r border-surface-600/60 bg-surface-800/70 backdrop-blur-xl transition-transform duration-200 ease-out",
        isOpen ? "pointer-events-auto translate-x-0" : "pointer-events-none -translate-x-full",
      )}
    >
      <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
        <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          {isEditing ? <LuPencilLine size={12} /> : <LuFiles size={12} />}
          {isEditing ? "Edit Inspection" : "New Inspection"}
        </div>
        <button
          type="button"
          onClick={closeNewInspectionDrawer}
          aria-label={isEditing ? "Close edit inspection form" : "Close new inspection form"}
          className="text-surface-400 hover:text-surface-100 outline-none"
        >
          <LuX size={14} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px] font-medium">Inspection Name</span>
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && submit()}
            placeholder="e.g. Winter dispatch review"
            className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 h-8 rounded border px-2 text-[13px] outline-none"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-surface-400 text-[11px] font-medium">Description</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Optional inspection context"
            rows={3}
            className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 resize-none rounded border px-2 py-1.5 text-[13px] outline-none"
          />
        </label>

        {!isEditing && (
          <div className="flex flex-col gap-1">
            <span className="text-surface-400 text-[11px] font-medium">Start From</span>
            <StartFromSelect
              value={startFrom}
              onValueChange={setStartFrom}
              inspections={inspections}
            />
            <span className="text-surface-500 text-[11px] leading-4">
              {startFrom === BLANK
                ? "Starts with one custom widget."
                : `Copies its widgets${inspections.some((inspection) => inspection.id === startFrom) ? ", result, comparison and filters" : ""}.`}{" "}
              You can add and remove widgets afterwards.
            </span>
          </div>
        )}
      </div>

      <div className="border-surface-600/60 flex shrink-0 justify-end gap-2 border-t p-3">
        <button
          type="button"
          onClick={closeNewInspectionDrawer}
          className="border-surface-600 text-surface-300 hover:bg-surface-700 rounded border px-3 py-1.5 text-[12px] font-medium outline-none"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={!name.trim()}
          className="bg-accent-600 hover:bg-accent-500 flex items-center gap-1.5 rounded px-3 py-1.5 text-[12px] font-medium text-white outline-none disabled:pointer-events-none disabled:opacity-50"
        >
          {isEditing ? null : <LuPlus size={13} />}
          {isEditing ? "Save" : "Create Inspection"}
        </button>
      </div>
    </aside>
  );
}
