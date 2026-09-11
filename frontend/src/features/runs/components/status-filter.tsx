import { Select } from "@base-ui/react/select";
import { FiCheck, FiChevronDown } from "react-icons/fi";
import { statusOptions } from "../status";
import type { RunStatus } from "../types";

type StatusFilterProps = {
  selectedStatuses: RunStatus[];
  onSelectedStatusesChange: (selectedStatuses: RunStatus[]) => void;
};

export function StatusFilter({ selectedStatuses, onSelectedStatusesChange }: StatusFilterProps) {
  const selectedStatusLabel =
    selectedStatuses.length > 0 ? `${selectedStatuses.length} selected` : "All statuses";

  return (
    <Select.Root<RunStatus, true>
      items={statusOptions}
      multiple
      value={selectedStatuses}
      onValueChange={onSelectedStatusesChange}
    >
      <Select.Trigger className="border-border bg-surface hover:bg-surface-alt data-[popup-open]:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-10 min-w-40 items-center justify-between gap-2 rounded-md border px-3 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2">
        <span>{selectedStatusLabel}</span>
        <Select.Icon>
          <FiChevronDown className="size-4" aria-hidden="true" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner align="end" className="z-10 outline-none" sideOffset={6}>
          <Select.Popup className="border-border bg-surface text-text shadow-primary/10 min-w-[var(--anchor-width)] rounded-md border py-1 shadow-xl transition-[opacity,scale] duration-100 ease-out outline-none data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
            <Select.List className="max-h-72 overflow-y-auto py-1">
              {statusOptions.map((status) => (
                <Select.Item className={selectItemClass} key={status.value} value={status.value}>
                  <Select.ItemIndicator className="text-primary">
                    <FiCheck className="size-4" aria-hidden="true" />
                  </Select.ItemIndicator>
                  <Select.ItemText>{status.label}</Select.ItemText>
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}

const selectItemClass =
  "grid cursor-default grid-cols-[1rem_1fr] items-center gap-2 px-3 py-2 text-sm outline-none select-none data-highlighted:bg-surface-alt";
