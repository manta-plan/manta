import { Tooltip } from "@base-ui/react/tooltip";
import type { IconType } from "react-icons";

// The icon buttons in a widget's header, each with the same tooltip.

/** The tooltip a widget header button shows; for triggers that aren't a WidgetIconButton, such as a menu. */
export function WidgetTooltipPopup({ label }: { label: string }) {
  return (
    <Tooltip.Portal>
      <Tooltip.Positioner sideOffset={8}>
        <Tooltip.Popup className="border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg">
          {label}
        </Tooltip.Popup>
      </Tooltip.Positioner>
    </Tooltip.Portal>
  );
}

/** `label` is the tooltip; `ariaLabel` names the button when it should say more, e.g. which widget. */
export function WidgetIconButton({
  icon: Icon,
  label,
  ariaLabel,
  pressed,
  onClick,
}: {
  icon: IconType;
  label: string;
  ariaLabel?: string;
  pressed?: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            onClick={onClick}
            aria-pressed={pressed}
            aria-label={ariaLabel ?? label}
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none ${pressed ? "bg-accent-600 text-white" : "text-surface-400 hover:bg-surface-700 hover:text-surface-50"}`}
          />
        }
      >
        <Icon size={14} />
      </Tooltip.Trigger>
      <WidgetTooltipPopup label={label} />
    </Tooltip.Root>
  );
}
