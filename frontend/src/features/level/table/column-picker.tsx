import { Popover } from "@base-ui/react/popover";
import { LuColumns3 } from "react-icons/lu";

// Which columns show. Hidden columns are remembered by their header across
// levels (a column hidden on Generator stays hidden on Solar), in this
// browser only. Hiding every column shows them all.

export function ColumnPicker({
  headers,
  hidden,
  onChange,
}: {
  /** Every column's header at this level. */ headers: string[];
  hidden: Set<string>;
  onChange: (hidden: string[]) => void;
}) {
  const hiddenHere = headers.filter((header) => hidden.has(header));
  const shown =
    hiddenHere.length === headers.length ? headers.length : headers.length - hiddenHere.length;
  const toggle = (header: string) =>
    onChange(
      hidden.has(header) ? [...hidden].filter((item) => item !== header) : [...hidden, header],
    );
  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label="Choose columns"
        title={hiddenHere.length ? `Columns (${hiddenHere.length} hidden)` : "Columns"}
        className={`focus-visible:border-accent-500 data-[popup-open]:border-accent-500 flex h-7 w-7 shrink-0 items-center justify-center rounded border outline-none ${
          hiddenHere.length
            ? "border-accent-500 text-accent-300"
            : "border-surface-600 text-surface-300 hover:border-surface-500 hover:text-surface-100"
        }`}
      >
        <LuColumns3 size={14} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner className="z-50 outline-none" side="bottom" align="end" sideOffset={6}>
          <Popover.Popup
            aria-label="Columns"
            className="border-surface-600 bg-surface-800 text-surface-100 flex max-h-[min(28rem,var(--available-height))] w-72 flex-col rounded-md border text-[12px] shadow-2xl shadow-black/50 outline-none"
          >
            <div className="border-surface-600/60 text-surface-400 shrink-0 border-b px-3 py-2 text-[10px] font-medium tracking-wide uppercase">
              Columns · {shown} of {headers.length} shown
            </div>
            <ul className="min-h-0 flex-1 overflow-auto py-1" aria-label="Columns">
              {headers.map((header) => (
                <li key={header}>
                  <label className="hover:bg-surface-700/60 flex cursor-pointer items-center gap-2 px-3 py-1">
                    <input
                      type="checkbox"
                      checked={!hidden.has(header)}
                      onChange={() => toggle(header)}
                      className="accent-accent-600"
                    />
                    <span className="min-w-0 flex-1 truncate">{header}</span>
                  </label>
                </li>
              ))}
            </ul>
            <div className="border-surface-600/60 flex shrink-0 items-center justify-between gap-2 border-t px-3 py-1.5">
              <button
                type="button"
                disabled={hiddenHere.length === 0}
                onClick={() => onChange([...hidden].filter((item) => !headers.includes(item)))}
                className="text-accent-300 focus-visible:ring-accent-500 disabled:text-surface-500 rounded px-1 text-[11px] outline-none hover:underline focus-visible:ring-1 disabled:no-underline"
              >
                Show all
              </button>
              <span className="text-surface-500 text-[11px]">
                Hidden columns keep their filters
              </span>
            </div>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
