import { Dialog } from "@base-ui/react/dialog";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  onConfirm: () => void;
  isConfirming?: boolean;
  confirmLabel?: string;
  confirmingLabel?: string;
  confirmDisabled?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  isConfirming = false,
  confirmLabel = "Remove",
  confirmingLabel = "Removing...",
  confirmDisabled = false,
}: ConfirmDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 w-[400px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl shadow-black/50 outline-none">
          <Dialog.Title className="text-surface-50 text-[14px] font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="text-surface-400 mt-2 text-[12px] leading-5">
            {description}
          </Dialog.Description>
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close
              disabled={isConfirming}
              className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 h-8 rounded px-3 text-[12px] font-medium outline-none disabled:opacity-50"
            >
              Cancel
            </Dialog.Close>
            <button
              type="button"
              onClick={onConfirm}
              disabled={isConfirming || confirmDisabled}
              className="bg-danger-500 hover:bg-danger-400 h-8 rounded px-3 text-[12px] font-medium text-white outline-none disabled:opacity-50"
            >
              {isConfirming ? confirmingLabel : confirmLabel}
            </button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
