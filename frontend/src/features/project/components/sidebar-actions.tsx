// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Tooltip } from "@base-ui/react/tooltip";
import { LuListFilter, LuPlus } from "react-icons/lu";

const tooltipClassName =
  "border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg";

// Icon buttons in a sidebar panel's header. They stop the pointer-down so that a header that
// resizes the panels (see Sidebar) does not start a resize from them.

export function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            aria-label={label}
            onClick={onClick}
            onPointerDown={(event) => event.stopPropagation()}
            className="text-surface-400 hover:text-surface-100 focus-visible:text-surface-100 outline-none"
          />
        }
      >
        <LuPlus size={13} />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className={tooltipClassName}>{label}</Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function FilterButton({
  label,
  onClick,
  isActive,
}: {
  label: string;
  onClick: () => void;
  isActive: boolean;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            aria-label={label}
            aria-pressed={isActive}
            onClick={onClick}
            onPointerDown={(event) => event.stopPropagation()}
            className={`outline-none ${isActive ? "text-accent-400" : "text-surface-400 hover:text-surface-100 focus-visible:text-surface-100"}`}
          />
        }
      >
        <LuListFilter size={13} />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className={tooltipClassName}>{label}</Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
