import { useEffect, useState } from "react";
import { LuDatabase, LuFolderPlus, LuX } from "react-icons/lu";
import { useLocation } from "wouter";
import { createProject } from "../api";
import { useAppStore } from "../store";
import { useRecordCatalogue } from "../lib/use-record-catalogue";
import { FormSelect } from "./form-select";

export function NewProjectDrawer() {
  const [location] = useLocation();
  const isOpen = useAppStore((s) => s.isNewProjectDrawerOpen);
  const closeNewProjectDrawer = useAppStore((s) => s.closeNewProjectDrawer);
  const addProject = useAppStore((s) => s.addProject);
  const setStatusMessage = useAppStore((s) => s.setStatusMessage);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const { catalogue, error } = useRecordCatalogue();
  const records = catalogue?.records ?? [];
  const [chosen, setChosen] = useState<string | null>("s3://manta/manual-test/input.nc");
  // The server's default until one is picked.
  const recordId = chosen ?? catalogue?.default ?? null;

  useEffect(() => {
    if (!isOpen) return;
    setName("");
    setDescription("");
    // setChosen(null);
  }, [isOpen]);

  useEffect(() => {
    if (location !== "/") closeNewProjectDrawer();
  }, [location, closeNewProjectDrawer]);

  // A project shows one record from the record server's catalogue.
  const canCreate = Boolean(name.trim() && recordId) && !isCreating;
  const handleCreate = async () => {
    if (!canCreate || !recordId) return;
    setIsCreating(true);
    try {
      // The backend owns the project; its uuid becomes the project's id here.
      const created = await createProject(name.trim(), description);
      const project = addProject(created.name, recordId, {
        uuid: created.uuid,
        description: created.description,
      });
      setStatusMessage(`${project.name} was created.`);
      closeNewProjectDrawer();
    } catch (error) {
      setStatusMessage(
        error instanceof Error
          ? `Couldn't create the project: ${error.message}`
          : "Couldn't create the project.",
      );
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <aside
      className={`border-surface-600 bg-surface-800 absolute top-0 right-0 z-20 flex h-full w-80 flex-col border-l shadow-2xl shadow-black/30 transition-transform duration-200 ease-out ${
        isOpen ? "translate-x-0" : "pointer-events-none translate-x-full"
      }`}
      aria-hidden={!isOpen}
    >
      <div className="border-surface-600 flex h-11 shrink-0 items-center justify-between border-b px-4">
        <div className="text-surface-100 flex items-center gap-2 text-[13px] font-medium">
          <LuFolderPlus size={15} className="text-accent-400" />
          New Project
        </div>
        <button
          onClick={closeNewProjectDrawer}
          aria-label="Close new project drawer"
          title="Close"
          className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 flex h-7 w-7 items-center justify-center rounded"
        >
          <LuX size={15} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-4 p-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-surface-400 text-[11px] font-medium">Project Name</span>
          <input
            autoFocus={isOpen}
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") handleCreate();
            }}
            placeholder="Project name"
            className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 h-8 rounded border px-2 text-[13px] outline-none"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-surface-400 text-[11px] font-medium">Description</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What is this project for? (optional)"
            rows={3}
            className="border-surface-600 bg-surface-900 text-surface-50 placeholder:text-surface-500 focus:border-accent-500 resize-none rounded border px-2 py-1.5 text-[13px] outline-none"
          />
        </label>
        <div className="flex flex-col gap-1.5">
          <span className="text-surface-400 text-[11px] font-medium">Data Record</span>
          <FormSelect
            ariaLabel="Data record"
            icon={LuDatabase}
            value={recordId}
            onValueChange={setChosen}
            options={records.map((record) => ({ value: record.id, label: record.label }))}
            disabled={records.length === 0}
            placeholder={
              error
                ? "Can't reach the record server"
                : catalogue
                  ? "No records available"
                  : "Loading records…"
            }
          />
          <span className="text-surface-500 text-[11px]">
            {records.find((record) => record.id === recordId)?.description ||
              "What the project shows: its network, scenarios and values."}
          </span>
        </div>
      </div>

      <div className="border-surface-600 flex shrink-0 justify-end gap-2 border-t p-4">
        <button
          onClick={closeNewProjectDrawer}
          className="text-surface-300 hover:bg-surface-700 h-8 rounded px-3 text-[12px] font-medium"
        >
          Cancel
        </button>
        <button
          onClick={handleCreate}
          disabled={!canCreate}
          className="bg-accent-600 hover:bg-accent-500 flex h-8 items-center gap-1.5 rounded px-3 text-[12px] font-medium text-white disabled:pointer-events-none disabled:opacity-50"
        >
          <LuFolderPlus size={14} />
          Create Project
        </button>
      </div>
    </aside>
  );
}
