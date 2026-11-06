import { Menu } from "@base-ui/react/menu";
import { Toolbar } from "@base-ui/react/toolbar";
import { Tooltip } from "@base-ui/react/tooltip";
import { LuChevronDown } from "react-icons/lu";
import type { IconType } from "react-icons";

export interface ToolbarModeOption<T extends string> {
  value: T;
  label: string;
  icon: IconType;
}

export function ToolbarModeMenu<T extends string>({
  label,
  options,
  value,
  onChange,
  triggerIcon,
  active,
  disabled,
  disabledHint,
  showLabel,
}: {
  label: string;
  options: ToolbarModeOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Fixed trigger icon; by default the trigger shows the selected option's icon. */
  triggerIcon?: IconType;
  /** Highlights the trigger, for menus that switch a map interaction on. */
  active?: boolean;
  /** Greys the trigger out; the tooltip still shows, with `disabledHint`. */
  disabled?: boolean;
  disabledHint?: string;
  /** Shows the selected option's label beside its icon, for a choice that should stay visible. */
  showLabel?: boolean;
}) {
  const current = options.find((o) => o.value === value) ?? options[0];
  const CurrentIcon = triggerIcon ?? current.icon;

  return (
    <Tooltip.Root>
      <Menu.Root>
        <Tooltip.Trigger
          render={
            <Menu.Trigger
              disabled={disabled}
              render={
                <Toolbar.Button
                  className={`flex h-7 items-center gap-0.5 rounded px-1.5 outline-none ${
                    disabled
                      ? "text-surface-500 cursor-default"
                      : active
                        ? "bg-accent-600 text-white"
                        : "text-surface-200 hover:bg-surface-700 hover:text-surface-50 data-[popup-open]:bg-surface-700 data-[popup-open]:text-surface-50"
                  }`}
                />
              }
            />
          }
        >
          <CurrentIcon size={16} strokeWidth={1.75} />
          {showLabel && (
            <span className="ml-1 max-w-[160px] truncate text-[12px]">{current.label}</span>
          )}
          <LuChevronDown
            size={10}
            className={
              active ? "text-white/70" : disabled ? "text-surface-600" : "text-surface-400"
            }
          />
        </Tooltip.Trigger>
        <Menu.Portal>
          <Menu.Positioner className="z-50 outline-none" sideOffset={4} align="start">
            <Menu.Popup className="border-surface-600 bg-surface-800 text-surface-100 min-w-[190px] rounded-md border py-1 text-[13px] shadow-2xl shadow-black/50 outline-none">
              <Menu.RadioGroup value={value} onValueChange={(v) => onChange(v as T)}>
                {options.map((opt) => {
                  const Icon = opt.icon;
                  return (
                    <Menu.RadioItem
                      key={opt.value}
                      value={opt.value}
                      className="data-[highlighted]:bg-accent-600 flex cursor-default items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:text-white"
                    >
                      <Icon size={14} className="shrink-0" />
                      <span>{opt.label}</span>
                    </Menu.RadioItem>
                  );
                })}
              </Menu.RadioGroup>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className="border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg">
            {label}: {current.label}
            {disabled && disabledHint ? (
              <span className="text-surface-400"> · {disabledHint}</span>
            ) : null}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
