// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";

// Shared by the draft scenario dialogs.
export const INPUT_CLASS =
  "h-8 w-full rounded border border-surface-600 bg-surface-900 px-2 text-[13px] text-surface-50 outline-none placeholder:text-surface-500 focus:border-accent-500";
export const PRIMARY_BUTTON_CLASS =
  "h-8 rounded bg-accent-600 px-3 text-[12px] font-medium text-white outline-none hover:bg-accent-500 disabled:opacity-50";
export const SECONDARY_BUTTON_CLASS =
  "h-8 rounded px-3 text-[12px] font-medium text-surface-300 outline-none hover:bg-surface-700 hover:text-surface-50";

export function DialogShell({
  open,
  onClose,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Popup className="border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 flex max-h-[calc(100vh-64px)] w-[440px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border shadow-2xl shadow-black/50 outline-none">
          <div className="px-5 pt-5">
            <Dialog.Title className="text-surface-50 text-[14px] font-semibold">
              {title}
            </Dialog.Title>
            {description && (
              <Dialog.Description className="text-surface-400 mt-1 text-[12px] leading-5">
                {description}
              </Dialog.Description>
            )}
          </div>
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto px-5 py-4">{children}</div>
          <div className="border-surface-700 flex items-center gap-2 border-t px-5 py-3">
            {footer}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-surface-400 text-[11px] font-medium">{label}</span>
      {children}
      {hint && <span className="text-surface-500 text-[11px] leading-4">{hint}</span>}
    </label>
  );
}
