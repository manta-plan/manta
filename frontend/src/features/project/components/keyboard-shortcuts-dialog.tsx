import { Dialog } from "@base-ui/react/dialog";
import { LuX } from "react-icons/lu";

// Single list for the dialog; the handlers live in Header's keydown effect.
const SHORTCUT_GROUPS: { title: string; items: { keys: string[]; label: string }[] }[] = [
  {
    title: "Navigation",
    items: [
      { keys: ["1"], label: "Model" },
      { keys: ["2"], label: "Run" },
    ],
  },
  {
    title: "Map (Model tab)",
    items: [
      { keys: ["L"], label: "Show or hide Map Layers" },
      { keys: ["+"], label: "Zoom in" },
      { keys: ["-"], label: "Zoom out" },
      { keys: ["Esc"], label: "Stop measuring" },
    ],
  },
  { title: "Help", items: [{ keys: ["?"], label: "Keyboard shortcuts" }] },
];

export function KeyboardShortcutsDialog({
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
        <Dialog.Popup className="border-surface-600 bg-surface-800 fixed top-1/2 left-1/2 z-40 w-[380px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-5 shadow-2xl shadow-black/50 outline-none">
          <div className="mb-1 flex items-center justify-between">
            <Dialog.Title className="text-surface-50 text-[14px] font-semibold">
              Keyboard Shortcuts
            </Dialog.Title>
            <Dialog.Close
              className="text-surface-400 hover:text-surface-100 outline-none"
              aria-label="Close"
            >
              <LuX size={16} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="text-surface-400 mb-4 text-[12px]">
            Shortcuts are off while you're typing in a field.
          </Dialog.Description>
          <div className="flex flex-col gap-4">
            {SHORTCUT_GROUPS.map((group) => (
              <section key={group.title}>
                <h3 className="text-surface-400 mb-1 text-[11px] font-medium">{group.title}</h3>
                <ul>
                  {group.items.map((item) => (
                    <li
                      key={item.label}
                      className="text-surface-100 flex items-center justify-between py-1 text-[13px]"
                    >
                      <span>{item.label}</span>
                      <span className="flex gap-1">
                        {item.keys.map((key) => (
                          <kbd
                            key={key}
                            className="border-surface-600 bg-surface-900 text-surface-200 min-w-6 rounded border px-1.5 py-0.5 text-center font-mono text-[11px]"
                          >
                            {key}
                          </kbd>
                        ))}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
