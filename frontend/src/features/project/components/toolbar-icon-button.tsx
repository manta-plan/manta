import { Toolbar } from "@base-ui/react/toolbar";
import { Tooltip } from "@base-ui/react/tooltip";
import type { IconType } from "react-icons";

export function ToolbarIconButton({
  icon: Icon,
  label,
  active,
  disabled,
  onClick,
  tourId,
}: {
  icon: IconType;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  tourId?: string;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <Toolbar.Button
            data-tour={tourId}
            onClick={onClick}
            disabled={disabled}
            aria-pressed={active}
            className={`group flex h-7 w-7 items-center justify-center rounded transition-colors outline-none ${
              active
                ? "bg-accent-600 text-white"
                : "text-surface-200 hover:bg-surface-700 hover:text-surface-50"
            } disabled:pointer-events-none disabled:opacity-40`}
          />
        }
      >
        <Icon size={16} strokeWidth={1.75} />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className="bg-surface-950 text-surface-100 border-surface-600 rounded border px-2 py-1 text-[11px] shadow-lg">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
