import { Menu } from "@base-ui/react/menu";
import { Toolbar } from "@base-ui/react/toolbar";
import { Tooltip } from "@base-ui/react/tooltip";
import { LuChevronDown } from "react-icons/lu";
import type { IconType } from "react-icons";

export interface ToolbarActionOption {
  label: string;
  icon: IconType;
  onSelect?: () => void;
}

export function ToolbarActionMenu({
  label,
  icon: TriggerIcon,
  options,
}: {
  label: string;
  icon: IconType;
  options: ToolbarActionOption[];
}) {
  return (
    <Tooltip.Root>
      <Menu.Root>
        <Tooltip.Trigger
          render={
            <Menu.Trigger
              render={
                <Toolbar.Button className="text-surface-200 hover:bg-surface-700 hover:text-surface-50 data-[popup-open]:bg-surface-700 data-[popup-open]:text-surface-50 flex h-7 items-center gap-0.5 rounded px-1.5 outline-none" />
              }
            />
          }
        >
          <TriggerIcon size={16} strokeWidth={1.75} />
          <LuChevronDown size={10} className="text-surface-400" />
        </Tooltip.Trigger>
        <Menu.Portal>
          <Menu.Positioner className="z-50 outline-none" sideOffset={4} align="start">
            <Menu.Popup className="border-surface-600 bg-surface-800 text-surface-100 min-w-[190px] rounded-md border py-1 text-[13px] shadow-2xl shadow-black/50 outline-none">
              {options.map((opt) => {
                const Icon = opt.icon;
                return (
                  <Menu.Item
                    key={opt.label}
                    onClick={opt.onSelect}
                    className="data-[highlighted]:bg-accent-600 flex cursor-default items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:text-white"
                  >
                    <Icon size={14} className="shrink-0" />
                    <span>{opt.label}</span>
                  </Menu.Item>
                );
              })}
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className="border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
