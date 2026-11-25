// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useId, type ReactNode } from "react";
import { motion } from "motion/react";
import type { IconType } from "react-icons";

// One component for every segmented switch, in two looks:
// - 'filled' (the default; Map | Graph, Statistics | Attributes, the dialogs'
//   and editors' switches): the app header's stage tabs — a dark track, the
//   chosen segment filled accent, the fill sliding between segments.
// - 'underline' (the investment period only, as in the modellers'
//   prototype): a bordered track, the chosen segment raised with a short
//   accent bar inset from its corners.

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  icon?: IconType;
  /** Greyed and not choosable; `title` says why. */
  disabled?: boolean;
  title?: string;
}

interface SegmentedProps<T extends string> {
  value: T;
  options: readonly SegmentedOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  /** 'tabs' when it switches what a panel shows (role tab, `panelId` it controls); else a radio group. */
  kind?: "radio" | "tabs";
  /** With kind 'tabs': the panel's id, and each tab gets `${idPrefix}-${value}`. */
  panelId?: string;
  idPrefix?: string;
  /** md is 32px tall (page heads), sm 28px (panels, toolbars). */
  size?: "sm" | "md";
  /** Segments share the track equally (fill its width, or equal columns for any count). */
  equal?: boolean;
  /** 'filled' (default) or 'underline' (the investment period). */
  variant?: "filled" | "underline";
  /** Inside the track after a divider, e.g. a caption. */
  suffix?: ReactNode;
  className?: string;
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  kind = "radio",
  panelId,
  idPrefix,
  size = "sm",
  equal = false,
  variant = "filled",
  suffix,
  className = "",
}: SegmentedProps<T>) {
  const isTabs = kind === "tabs";
  const filled = variant === "filled";
  // The sliding fill's shared id, one per switch.
  const fillId = useId();
  return (
    <div
      className={`bg-surface-900 flex max-w-full items-stretch gap-0.5 rounded-md p-0.5 ${filled ? "" : "border-surface-600 border"} ${size === "md" ? "h-8" : "h-7"} ${className}`}
    >
      <div
        role={isTabs ? "tablist" : "radiogroup"}
        aria-label={ariaLabel}
        className={`min-w-0 gap-0.5 overflow-x-auto ${equal ? "grid flex-1 auto-cols-fr grid-flow-col" : "flex"}`}
      >
        {options.map((option) => {
          const active = option.value === value;
          const Icon = option.icon;
          return (
            <button
              key={option.value}
              type="button"
              role={isTabs ? "tab" : "radio"}
              id={isTabs && idPrefix ? `${idPrefix}-${option.value}` : undefined}
              aria-selected={isTabs ? active : undefined}
              aria-checked={isTabs ? undefined : active}
              aria-controls={isTabs ? panelId : undefined}
              // aria-disabled, not disabled: a disabled button shows no tooltip.
              aria-disabled={option.disabled || undefined}
              title={option.title}
              onClick={() => !option.disabled && !active && onChange(option.value)}
              className={`focus-visible:ring-accent-500 relative isolate flex items-center justify-center gap-1.5 rounded px-2.5 text-[12px] leading-none font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-1 ${
                size === "md" ? "min-w-14 px-3 tabular-nums" : ""
              } ${
                option.disabled
                  ? "text-surface-600 cursor-not-allowed"
                  : filled
                    ? // Fixed white on the fill: it's the brand accent in both themes (as the stage tabs).
                      active
                      ? "text-white"
                      : "text-surface-300 hover:text-surface-100"
                    : active
                      ? "bg-surface-700 text-surface-50"
                      : "text-surface-400 hover:bg-surface-800 hover:text-surface-100"
              }`}
            >
              {filled && active && (
                <motion.span
                  aria-hidden
                  layoutId={fillId}
                  transition={{ type: "spring", bounce: 0.15, duration: 0.3 }}
                  className="bg-accent-600 absolute inset-0 -z-10 rounded"
                />
              )}
              {Icon && <Icon size={13} aria-hidden />}
              {option.label}
              {!filled && active && (
                <span
                  aria-hidden
                  className="bg-accent-400 absolute inset-x-2 bottom-0.5 h-0.5 rounded-full"
                />
              )}
            </button>
          );
        })}
      </div>
      {suffix && (
        <>
          <span aria-hidden className="bg-surface-700 my-1 w-px shrink-0" />
          <div className="text-surface-400 flex shrink-0 items-center px-2">{suffix}</div>
        </>
      )}
    </div>
  );
}
