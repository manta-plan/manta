// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Toast } from "@base-ui/react/toast";

// The app's toasts: short, non-blocking notes about something that just
// happened, with an action or two. Raised from anywhere with showToast;
// AppToasts (at the app's root) draws them.

export const toastManager = Toast.createToastManager();

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastData {
  /** Buttons besides the main action (`action`), e.g. Rename next to Undo. */
  extraActions?: ToastAction[];
}

export function showToast({
  title,
  description,
  action,
  extraActions,
  timeout = 8000,
}: {
  title: string;
  description?: string;
  action?: ToastAction;
  extraActions?: ToastAction[];
  timeout?: number;
}) {
  return toastManager.add<ToastData>({
    title,
    description,
    timeout,
    actionProps: action ? { children: action.label, onClick: action.onClick } : undefined,
    data: { extraActions },
  });
}
