import { useEffect, useState } from "react";
import { LuFolderPen, LuX } from "react-icons/lu";
import { updateProject } from "../api";
import { isLocalProjectId, useAppStore } from "../store";

export function RenameProjectDrawer() {
  const project = useAppStore((s) => s.projectToRename);
  const closeRenameProjectDrawer = useAppStore((s) => s.closeRenameProjectDrawer);
  const renameProject = useAppStore((s) => s.renameProject);
  const setStatusMessage = useAppStore((s) => s.setStatusMessage);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setName(project?.name ?? "");
    setDescription(project?.description ?? "");
  }, [project]);

  const canRename = Boolean(name.trim()) && !isSaving;
  const handleRename = async () => {
    if (!project || !canRename) return;
    setIsSaving(true);
    try {
      // Projects made before the backend stored them only exist in this browser.
      const saved = isLocalProjectId(project.id)
        ? { name: name.trim(), description }
        : await updateProject(project.id, name.trim(), description);
      renameProject(project.id, saved.name, saved.description ?? "");
      setStatusMessage(`${saved.name} was renamed.`);
      closeRenameProjectDrawer();
    } catch (error) {
      setStatusMessage(
        error instanceof Error
          ? `Couldn't rename the project: ${error.message}`
          : "Couldn't rename the project.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <aside
      className={`border-surface-600 bg-surface-800 absolute top-0 right-0 z-20 flex h-full w-80 flex-col border-l shadow-2xl shadow-black/30 transition-transform duration-200 ease-out ${
        project ? "translate-x-0" : "pointer-events-none translate-x-full"
      }`}
      aria-hidden={!project}
    >
      <div className="border-surface-600 flex h-11 shrink-0 items-center justify-between border-b px-4">
        <div className="text-surface-100 flex items-center gap-2 text-[13px] font-medium">
          <LuFolderPen size={15} className="text-accent-400" />
          Rename Project
        </div>
        <button
          onClick={closeRenameProjectDrawer}
          aria-label="Close rename project drawer"
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
            autoFocus={Boolean(project)}
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void handleRename();
            }}
            className="border-surface-600 bg-surface-900 text-surface-50 focus:border-accent-500 h-8 rounded border px-2 text-[13px] outline-none"
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
      </div>

      <div className="border-surface-600 flex shrink-0 justify-end gap-2 border-t p-4">
        <button
          onClick={closeRenameProjectDrawer}
          className="text-surface-300 hover:bg-surface-700 h-8 rounded px-3 text-[12px] font-medium"
        >
          Cancel
        </button>
        <button
          onClick={() => void handleRename()}
          disabled={!canRename}
          className="bg-accent-600 hover:bg-accent-500 h-8 rounded px-3 text-[12px] font-medium text-white disabled:pointer-events-none disabled:opacity-50"
        >
          Rename
        </button>
      </div>
    </aside>
  );
}
