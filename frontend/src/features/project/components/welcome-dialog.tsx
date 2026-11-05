import { useEffect, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useLocation, useParams } from "wouter";
import { FaFly } from "react-icons/fa";
import { GiMagnifyingGlass } from "react-icons/gi";
import { LuBoxes, LuHistory } from "react-icons/lu";
import type { IconType } from "react-icons";
import { useAppStore } from "../../home/store";
import { useProjectStore } from "../store/project-store";
import { projectTabHref } from "../lib/project-route";
import { startModelWorkspaceTour } from "../lib/workspace-tours";
import { isWelcomeDialogDisabled, setWelcomeDialogDisabled } from "../lib/welcome-preference";

// Same icons as the Sidebar panels, so the overview maps onto what the user sees.
const WORKSPACES: { label: string; description: string; icon: IconType }[] = [
  {
    label: "Model",
    description: "Browse the network and edit scenarios as mutations.",
    icon: LuBoxes,
  },
  {
    label: "Run",
    description: "Execute a playbook against a scenario and track its progress.",
    icon: LuHistory,
  },
  {
    label: "Inspect",
    description: "Explore and compare run outputs as tables, maps and charts.",
    icon: GiMagnifyingGlass,
  },
];

// Gives the dialog's close transition and the tab switch a moment to settle
// before driver.js measures the tour targets.
const TOUR_START_DELAY_MS = 150;

export function WelcomeDialog() {
  const [, setLocation] = useLocation();
  const { projectId } = useParams<{ projectId: string }>();
  const isOpen = useProjectStore((s) => s.isWelcomeDialogOpen);
  const closeWelcomeDialog = useProjectStore((s) => s.closeWelcomeDialog);
  const dismissProjectWelcome = useAppStore((s) => s.dismissProjectWelcome);
  const projectName = useAppStore(
    (s) => s.projects.find((project) => project.id === projectId)?.name,
  );
  const [dontShowAgain, setDontShowAgain] = useState(false);

  useEffect(() => {
    if (isOpen) setDontShowAgain(isWelcomeDialogDisabled());
  }, [isOpen]);

  // Every way out (Close, Start tour, Escape, backdrop) counts as seen for
  // this project, and saves the checkbox as the global preference.
  const dismiss = () => {
    dismissProjectWelcome(projectId);
    setWelcomeDialogDisabled(dontShowAgain);
    closeWelcomeDialog();
  };

  const startTour = () => {
    dismiss();
    setLocation(projectTabHref(projectId, "model"));
    window.setTimeout(startModelWorkspaceTour, TOUR_START_DELAY_MS);
  };

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && dismiss()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 w-[440px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl shadow-black/50 outline-none">
          <Dialog.Title className="text-surface-50 text-[15px] font-semibold">
            Welcome to {projectName ?? "your project"}
          </Dialog.Title>
          <Dialog.Description className="text-surface-400 mt-1.5 text-[12px] leading-5">
            A project has three workspaces so far: the model, its runs and their results.
          </Dialog.Description>

          <ol className="mt-4 flex flex-col gap-3">
            {WORKSPACES.map(({ label, description, icon: Icon }, index) => (
              <li key={label} className="flex items-center gap-3">
                <span className="border-surface-600 bg-surface-900 text-accent-400 flex h-7 w-7 shrink-0 items-center justify-center rounded border">
                  <Icon size={14} />
                </span>
                <div className="min-w-0">
                  <div className="text-surface-100 text-[12px] font-medium">
                    <span className="text-surface-500">{index + 1}.</span> {label}
                  </div>
                  <div className="text-surface-400 text-[12px] leading-5">{description}</div>
                </div>
              </li>
            ))}
          </ol>

          <div className="mt-5 flex items-center gap-3">
            <label className="text-surface-300 mr-auto flex cursor-pointer items-center gap-2 text-[12px] select-none">
              <input
                type="checkbox"
                checked={dontShowAgain}
                onChange={(event) => setDontShowAgain(event.target.checked)}
                className="accent-accent-500 h-3.5 w-3.5"
              />
              Don't show this again
            </label>
            <button
              type="button"
              onClick={dismiss}
              className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 h-8 rounded px-3 text-[12px] font-medium outline-none"
            >
              Close
            </button>
            <button
              type="button"
              onClick={startTour}
              className="bg-accent-600 hover:bg-accent-500 flex h-8 items-center gap-1.5 rounded px-3 text-[12px] font-medium text-white outline-none"
            >
              <FaFly size={13} />
              Start tour
            </button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
