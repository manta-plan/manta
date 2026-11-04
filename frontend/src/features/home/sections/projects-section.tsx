import { useState } from "react";
import { LuEllipsis, LuFolder, LuFolderPlus, LuPencil, LuTrash2 } from "react-icons/lu";
import { Menu } from "@base-ui/react/menu";
import { Link } from "wouter";
import { useAppStore } from "../store";
import { HomeSectionFrame } from "../components/home-primitives";
import { SectionHeader } from "../components/section-header";
import { ConfirmDialog } from "../components/confirm-dialog";

export function ProjectsSection() {
  const projects = useAppStore((s) => s.projects);
  const openNewProjectDrawer = useAppStore((s) => s.openNewProjectDrawer);
  const openRenameProjectDrawer = useAppStore((s) => s.openRenameProjectDrawer);
  const removeProject = useAppStore((s) => s.removeProject);
  const setStatusMessage = useAppStore((s) => s.setStatusMessage);
  const [removingProjectId, setRemovingProjectId] = useState<string | null>(null);
  const [projectToRemove, setProjectToRemove] = useState<{ id: string; name: string } | null>(null);

  const confirmRemoveProject = async () => {
    if (!projectToRemove) return;
    const { id: projectId, name: projectName } = projectToRemove;
    setRemovingProjectId(projectId);
    try {
      await removeProject(projectId);
      setStatusMessage(`${projectName} was removed.`);
      setProjectToRemove(null);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : `Could not remove ${projectName}.`);
    } finally {
      setRemovingProjectId(null);
    }
  };

  return (
    <HomeSectionFrame>
      <SectionHeader
        title="Projects"
        description="Energy system models you own or collaborate on."
        action={
          <button
            onClick={openNewProjectDrawer}
            className="bg-accent-600 hover:bg-accent-500 flex h-8 items-center gap-1.5 rounded px-3 text-[12px] font-medium text-white"
          >
            <LuFolderPlus size={14} />
            New Project
          </button>
        }
      />

      {projects.length === 0 ? (
        <div className="border-surface-600 flex min-h-64 flex-col items-center justify-center border-y border-dashed px-6 text-center">
          <div className="bg-accent-600/15 text-accent-400 flex h-10 w-10 items-center justify-center rounded-full">
            <LuFolder size={18} />
          </div>
          <h2 className="text-surface-100 mt-3 text-[14px] font-medium">No projects yet</h2>
          <p className="text-surface-400 mt-1 max-w-sm text-[12px] leading-5">
            Create a project to explore the record on the record server.
          </p>
          <button
            onClick={openNewProjectDrawer}
            className="bg-accent-600 hover:bg-accent-500 mt-4 flex h-8 items-center gap-1.5 rounded px-3 text-[12px] font-medium text-white"
          >
            <LuFolderPlus size={14} />
            New Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
          {projects.map((project) => (
            <div
              key={project.id}
              className="group border-surface-700 bg-surface-800 hover:border-accent-500 relative rounded-lg border transition-colors"
            >
              <Link
                href={`/project/${project.id}`}
                className="flex min-h-[104px] flex-col gap-3 p-4 text-left"
              >
                <LuFolder size={22} className="text-accent-400" />
                <div className="min-w-0">
                  <div className="text-surface-50 truncate pr-7 text-[13px] font-medium">
                    {project.name}
                  </div>
                  <div className="text-surface-400 mt-0.5 text-[11px]">
                    Edited {project.lastModified}
                  </div>
                </div>
              </Link>
              <Menu.Root>
                <Menu.Trigger
                  aria-label={`Open actions for ${project.name}`}
                  title="Actions"
                  disabled={removingProjectId === project.id}
                  className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 absolute top-2 right-2 flex h-7 w-7 items-center justify-center rounded opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-50"
                >
                  <LuEllipsis size={16} />
                </Menu.Trigger>
                <Menu.Portal>
                  <Menu.Positioner className="outline-none" sideOffset={4} align="end">
                    <Menu.Popup className="border-surface-600 bg-surface-800 text-surface-100 min-w-[200px] rounded-md border py-1 text-[13px] shadow-2xl shadow-black/50 outline-none">
                      <Menu.Item
                        onClick={() =>
                          openRenameProjectDrawer({ id: project.id, name: project.name })
                        }
                        className="data-[highlighted]:bg-accent-600 flex cursor-default items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:text-white"
                      >
                        <LuPencil size={14} />
                        <span>Rename</span>
                      </Menu.Item>
                      <Menu.Item
                        onClick={() => setProjectToRemove({ id: project.id, name: project.name })}
                        className="text-danger-500 data-[highlighted]:bg-danger-500 flex cursor-default items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:text-white"
                      >
                        <LuTrash2 size={14} />
                        <span>Remove</span>
                      </Menu.Item>
                    </Menu.Popup>
                  </Menu.Positioner>
                </Menu.Portal>
              </Menu.Root>
            </div>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={Boolean(projectToRemove)}
        onOpenChange={(open) => !open && !removingProjectId && setProjectToRemove(null)}
        title="Remove Project"
        description={projectToRemove ? `Remove ${projectToRemove.name}?` : ""}
        onConfirm={() => void confirmRemoveProject()}
        isConfirming={Boolean(removingProjectId)}
      />
    </HomeSectionFrame>
  );
}
