import { Dialog } from "@base-ui/react/dialog";
import { format } from "date-fns";
import { LuX } from "react-icons/lu";
import { MantaLogo } from "../../home/components/manta-logo";

// The commit date as YYYY-MM-DD in the viewer's time zone, or "" if unknown.
function commitDate() {
  const date = new Date(__APP_COMMIT_DATE__);
  return Number.isNaN(date.getTime()) ? "" : format(date, "yyyy-MM-dd");
}

// Shows which build is running: the git commit it was built from and that
// commit's date. Credits can go here later.
export function AboutDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 w-[360px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl shadow-black/50 outline-none">
          <div className="flex justify-end">
            <Dialog.Close
              className="text-surface-400 hover:text-surface-100 outline-none"
              aria-label="Close"
            >
              <LuX size={16} />
            </Dialog.Close>
          </div>
          <div className="flex flex-col items-center gap-2 pb-4 text-center">
            <MantaLogo />
            <Dialog.Title className="sr-only">About Manta</Dialog.Title>
            <Dialog.Description className="text-surface-400 text-[12px]">
              Work in progress
            </Dialog.Description>
            <p className="text-surface-400 text-[12px]">
              Commit <span className="text-surface-200 font-mono">{__APP_VERSION__}</span>
              {commitDate() && <> · {commitDate()}</>}
            </p>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
