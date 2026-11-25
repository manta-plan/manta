import { useEffect, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";

// Names a new inspection saved from the inspection page.
export function InspectionNameDialog({
  open,
  onOpenChange,
  title,
  description,
  initialName = "",
  confirmLabel,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  initialName?: string;
  confirmLabel: string;
  onConfirm: (name: string) => void;
}) {
  const [name, setName] = useState(initialName);

  useEffect(() => {
    if (open) setName(initialName);
  }, [open, initialName]);

  const submit = () => {
    if (name.trim()) onConfirm(name.trim());
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 w-[400px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl shadow-black/50 outline-none">
          <Dialog.Title className="text-surface-50 text-[14px] font-semibold">{title}</Dialog.Title>
          {description && (
            <Dialog.Description className="text-surface-400 mt-2 text-[12px] leading-5">
              {description}
            </Dialog.Description>
          )}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <label className="mt-4 flex flex-col gap-1.5">
              <span className="text-surface-400 text-[11px]">Name</span>
              <input
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Winter adequacy check"
                className="border-surface-600 bg-surface-900 text-surface-50 focus:border-accent-500 h-8 rounded border px-2 text-[12px] outline-none"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <Dialog.Close className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 h-8 rounded px-3 text-[12px] font-medium outline-none">
                Cancel
              </Dialog.Close>
              <button
                type="submit"
                disabled={!name.trim()}
                className="bg-accent-600 hover:bg-accent-500 h-8 rounded px-3 text-[12px] font-medium text-white outline-none disabled:opacity-50"
              >
                {confirmLabel}
              </button>
            </div>
          </form>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
