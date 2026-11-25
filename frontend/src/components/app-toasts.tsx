import type { ReactNode } from "react";
import { Toast } from "@base-ui/react/toast";
import { LuX } from "react-icons/lu";
import { toastManager, type ToastData } from "../utils/toasts";

// Draws the toasts raised with showToast, stacked bottom-right.

function ToastList() {
  const { toasts, close } = Toast.useToastManager<ToastData>();
  return toasts.map((toast) => (
    <Toast.Root
      key={toast.id}
      toast={toast}
      className="border-surface-600 bg-surface-800 text-surface-100 pointer-events-auto flex w-80 items-start gap-3 rounded-md border px-3 py-2.5 shadow-2xl shadow-black/40 transition-[opacity,transform] duration-200 data-[ending-style]:translate-y-2 data-[ending-style]:opacity-0 data-[starting-style]:translate-y-2 data-[starting-style]:opacity-0"
    >
      <div className="min-w-0 flex-1">
        <Toast.Title className="text-surface-50 text-[12px] font-medium" />
        <Toast.Description className="text-surface-400 mt-0.5 text-[11px] leading-4" />
        {(toast.actionProps || (toast.data?.extraActions?.length ?? 0) > 0) && (
          <div className="mt-2 flex gap-1.5">
            {toast.actionProps && (
              <Toast.Action className="bg-accent-600 hover:bg-accent-500 focus-visible:ring-accent-300 h-6 rounded px-2 text-[11px] font-medium text-white outline-none focus-visible:ring-1" />
            )}
            {toast.data?.extraActions?.map((action) => (
              <button
                key={action.label}
                type="button"
                onClick={() => {
                  action.onClick();
                  close(toast.id);
                }}
                className="border-surface-600 text-surface-200 hover:bg-surface-700 focus-visible:border-accent-500 h-6 rounded border px-2 text-[11px] font-medium outline-none"
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <Toast.Close
        aria-label="Dismiss"
        className="text-surface-400 hover:bg-surface-700 hover:text-surface-100 -mr-1 flex h-5 w-5 shrink-0 items-center justify-center rounded outline-none"
      >
        <LuX size={12} />
      </Toast.Close>
    </Toast.Root>
  ));
}

export function AppToasts({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider toastManager={toastManager} limit={3}>
      {children}
      <Toast.Portal>
        <Toast.Viewport className="pointer-events-none fixed right-4 bottom-10 z-[60] flex flex-col items-end gap-2 outline-none">
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  );
}
