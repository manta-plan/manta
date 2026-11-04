import { Select } from "@base-ui/react/select";
import type { IconType } from "react-icons";
import { LuCheck, LuChevronDown } from "react-icons/lu";

export interface FormSelectOption {
  value: string;
  label: string;
}

/**
 * Base UI select styled for drawer forms (h-8 field, matching text inputs).
 * Passes the options as `items`, so the closed trigger shows the option's
 * label rather than its raw value.
 */
export function FormSelect({
  value,
  onValueChange,
  options,
  disabled,
  placeholder,
  icon: Icon,
  ariaLabel,
}: {
  value: string | null;
  onValueChange: (value: string) => void;
  options: FormSelectOption[];
  disabled?: boolean;
  placeholder?: string;
  /** Optional leading icon inside the trigger. */
  icon?: IconType;
  /** For selects without a wrapping <label>. */
  ariaLabel?: string;
}) {
  return (
    <Select.Root
      value={value}
      onValueChange={(next) => next !== null && onValueChange(next)}
      items={options}
      disabled={disabled}
    >
      <Select.Trigger
        aria-label={ariaLabel}
        className="border-surface-600 bg-surface-900 text-surface-50 focus-visible:border-accent-500 flex h-8 items-center gap-2 rounded border px-2 text-left text-[13px] outline-none data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
      >
        {Icon && <Icon size={14} className="text-surface-400 shrink-0" />}
        <Select.Value
          className="data-[placeholder]:text-surface-500 min-w-0 flex-1 truncate"
          placeholder={placeholder}
        />
        <Select.Icon className="text-surface-400">
          <LuChevronDown size={13} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner sideOffset={6} align="start" className="z-50">
          <Select.Popup className="border-surface-600 bg-surface-800 min-w-[var(--anchor-width)] overflow-hidden rounded border p-1 shadow-xl outline-none">
            <Select.List>
              {options.map((option) => (
                <Select.Item
                  key={option.value}
                  value={option.value}
                  className="text-surface-200 data-[highlighted]:bg-surface-700 data-[selected]:text-surface-50 flex h-8 cursor-default items-center gap-2 rounded px-2 text-[12px] outline-none"
                >
                  <Select.ItemText className="min-w-0 flex-1 truncate">
                    {option.label}
                  </Select.ItemText>
                  <Select.ItemIndicator className="text-accent-400">
                    <LuCheck size={13} />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}
