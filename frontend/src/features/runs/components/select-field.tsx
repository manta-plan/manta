import { Select } from "@base-ui/react/select";
import { FiCheck, FiChevronDown } from "react-icons/fi";

export type SelectFieldItem = { label: string; value: string };

type SelectFieldProps = {
  id: string;
  items: SelectFieldItem[];
  // null shows the placeholder.
  value: string | null;
  placeholder?: string;
  onValueChange: (value: string) => void;
};

export function SelectField({
  id,
  items,
  value,
  placeholder = "Select an option",
  onValueChange,
}: SelectFieldProps) {
  return (
    <Select.Root
      items={items}
      onValueChange={(next) => {
        if (next !== null) {
          onValueChange(next);
        }
      }}
      value={value}
    >
      <Select.Trigger
        className="border-border bg-surface text-text focus-visible:outline-secondary inline-flex h-10 w-full items-center justify-between gap-2 rounded-md border px-3 text-sm transition focus-visible:outline-2 focus-visible:outline-offset-2"
        id={id}
      >
        <Select.Value placeholder={placeholder} />
        <Select.Icon>
          <FiChevronDown className="size-4" aria-hidden="true" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner
          alignItemWithTrigger={false}
          className="z-30 outline-none"
          sideOffset={6}
        >
          <Select.Popup className="border-border bg-surface text-text max-h-72 min-w-[var(--anchor-width)] overflow-y-auto rounded-md border py-1 shadow-xl outline-none">
            <Select.List>
              {items.map((item) => (
                <Select.Item
                  className="data-highlighted:bg-surface-alt grid cursor-default grid-cols-[1rem_1fr] items-center gap-2 px-3 py-2 text-sm outline-none"
                  key={item.value}
                  value={item.value}
                >
                  <Select.ItemIndicator className="text-primary">
                    <FiCheck className="size-4" aria-hidden="true" />
                  </Select.ItemIndicator>
                  <Select.ItemText className="col-start-2">{item.label}</Select.ItemText>
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}
