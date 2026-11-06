import { Menu } from "@base-ui/react/menu";

export interface MenuAction {
  label: string;
  shortcut?: string;
  separatorAfter?: boolean;
  disabled?: boolean;
  onSelect?: () => void;
}

export function MenuDropdown({ label, items }: { label: string; items: MenuAction[] }) {
  return (
    <Menu.Root>
      <Menu.Trigger className="text-surface-200 hover:bg-surface-700 data-[popup-open]:bg-surface-700 data-[popup-open]:text-surface-50 rounded px-2.5 py-1 text-[13px] outline-none">
        {label}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner className="z-50 outline-none" sideOffset={4} align="start">
          <Menu.Popup className="border-surface-600 bg-surface-800 text-surface-100 min-w-[220px] rounded-md border py-1 text-[13px] shadow-2xl shadow-black/50 outline-none">
            {items.map((item, i) => (
              <div key={item.label + i}>
                <Menu.Item
                  disabled={item.disabled}
                  onClick={item.onSelect}
                  className="data-[highlighted]:bg-accent-600 data-[disabled]:text-surface-500 flex cursor-default items-center justify-between gap-8 px-3 py-1.5 outline-none data-[highlighted]:text-white"
                >
                  <span>{item.label}</span>
                  {item.shortcut && (
                    <span className="text-surface-400 text-[11px]">{item.shortcut}</span>
                  )}
                </Menu.Item>
                {item.separatorAfter && <Menu.Separator className="bg-surface-600 my-1 h-px" />}
              </div>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
