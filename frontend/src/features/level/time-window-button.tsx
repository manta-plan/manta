import { useState } from "react";
import { Popover } from "@base-ui/react/popover";
import { LuClock3, LuX } from "react-icons/lu";
import { useLevelStore, type TimeWindow } from "./level-store";
import { usePeriods, type PeriodSpan } from "./periods";

// The time window inside the investment period: its full span, a
// meteorological season, or a custom range of at least two hours. It slices
// every time series and what's summed over hours. Global, like the period.

const DAY_MS = 24 * 3600 * 1000;
const HOUR_MS = 3600 * 1000;
const MIN_HOURS = 2;

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const SEASONS = [
  { label: "Winter", months: [11, 0, 1] },
  { label: "Spring", months: [2, 3, 4] },
  { label: "Summer", months: [5, 6, 7] },
  { label: "Autumn", months: [8, 9, 10] },
] as const;

function dayLabel(ms: number) {
  const date = new Date(ms);
  return `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
}

/** "Mon 7 Jan – Sun 13 Jan" for [start, end). */
function rangeLabel(start: number, end: number) {
  const last = end - HOUR_MS;
  return Math.floor(start / DAY_MS) === Math.floor(last / DAY_MS)
    ? dayLabel(start)
    : `${dayLabel(start)} – ${dayLabel(last)}`;
}

const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
/** For a datetime-local input (UTC shown as is). */
const inputValue = (ms: number) => new Date(ms).toISOString().slice(0, 16);
const fromInput = (value: string) => Date.parse(`${value}:00Z`);

/** The season inside the period's span, as one window from its first to its last hour there; null when the span has none of it. */
function seasonWindow(
  span: PeriodSpan,
  months: readonly number[],
  label: string,
): TimeWindow | null {
  const start = Date.parse(span.start);
  const end = Date.parse(span.end) + HOUR_MS;
  // Winter wraps the year: from December of the span's first year, else the span's start.
  let first: number | null = null;
  let last: number | null = null;
  for (let day = Math.floor(start / DAY_MS) * DAY_MS; day < end; day += DAY_MS) {
    if (!months.includes(new Date(day).getUTCMonth())) continue;
    first ??= Math.max(day, start);
    last = Math.min(day + DAY_MS, end);
  }
  if (first === null || last === null || last - first < MIN_HOURS * HOUR_MS) return null;
  return { start: iso(first), end: iso(last), label };
}

export function TimeWindowButton() {
  const { span } = usePeriods();
  const timeWindow = useLevelStore((s) => s.timeWindow);
  const setTimeWindow = useLevelStore((s) => s.setTimeWindow);
  const [open, setOpen] = useState(false);
  if (!span) return null;
  const spanStart = Date.parse(span.start);
  const spanEnd = Date.parse(span.end) + HOUR_MS;
  const label = timeWindow?.label ?? rangeLabel(spanStart, spanEnd);
  const seasons = SEASONS.map((season) => seasonWindow(span, season.months, season.label)).filter(
    (item): item is TimeWindow => item !== null,
  );

  return (
    <div className="flex items-center">
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger
          title="Time window"
          className={`focus-visible:border-accent-500 flex h-8 items-center gap-1.5 border px-2.5 text-[12px] outline-none ${
            timeWindow
              ? "border-accent-500/60 bg-accent-600/20 text-accent-300 rounded-l-md"
              : "border-surface-600 bg-surface-900 text-surface-300 hover:text-surface-100 rounded-md"
          }`}
        >
          <LuClock3 size={13} />
          {label}
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Positioner
            className="z-50 outline-none"
            side="bottom"
            align="start"
            sideOffset={6}
          >
            <Popover.Popup className="border-surface-600 bg-surface-800 text-surface-100 flex w-72 flex-col gap-1 rounded-md border p-2 text-[12px] shadow-2xl shadow-black/50 outline-none">
              <WindowOption
                label="Full span"
                detail={rangeLabel(spanStart, spanEnd)}
                active={!timeWindow}
                onSelect={() => (setTimeWindow(null), setOpen(false))}
              />
              {seasons.length > 0 && (
                <div className="text-surface-500 px-2 pt-2 pb-0.5 text-[10px] font-medium tracking-wide uppercase">
                  Meteorological season
                </div>
              )}
              {seasons.map((season) => (
                <WindowOption
                  key={season.label}
                  label={season.label}
                  detail={rangeLabel(Date.parse(season.start), Date.parse(season.end))}
                  active={timeWindow?.label === season.label}
                  onSelect={() => (setTimeWindow(season), setOpen(false))}
                />
              ))}
              <CustomRange
                spanStart={spanStart}
                spanEnd={spanEnd}
                current={timeWindow}
                onApply={(window) => (setTimeWindow(window), setOpen(false))}
              />
              <p className="text-surface-500 px-2 pt-1 text-[10px] leading-snug">
                The window slices every time series, and figures summed over hours are scaled to a
                year.
              </p>
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>
      {timeWindow && (
        <button
          type="button"
          aria-label="Reset to the full span"
          title="Reset to the full span"
          onClick={() => setTimeWindow(null)}
          className="border-accent-500/60 bg-accent-600/20 text-accent-300 hover:text-surface-50 focus-visible:border-accent-500 flex h-8 w-8 items-center justify-center rounded-r-md border border-l-0 outline-none"
        >
          <LuX size={11} />
        </button>
      )}
    </div>
  );
}

function WindowOption({
  label,
  detail,
  active,
  onSelect,
}: {
  label: string;
  detail: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`hover:bg-surface-700 focus-visible:bg-surface-700 flex items-center justify-between gap-3 rounded px-2 py-1.5 text-left outline-none ${active ? "text-accent-300" : ""}`}
    >
      <span className="font-medium">{label}</span>
      <span className="text-surface-400 text-[11px]">{detail}</span>
    </button>
  );
}

function CustomRange({
  spanStart,
  spanEnd,
  current,
  onApply,
}: {
  spanStart: number;
  spanEnd: number;
  current: TimeWindow | null;
  onApply: (window: TimeWindow) => void;
}) {
  const [from, setFrom] = useState(() =>
    inputValue(current ? Date.parse(current.start) : spanStart),
  );
  const [to, setTo] = useState(() => inputValue(current ? Date.parse(current.end) : spanEnd));
  const start = Math.max(spanStart, fromInput(from));
  const end = Math.min(spanEnd, fromInput(to));
  const valid =
    Number.isFinite(start) && Number.isFinite(end) && end - start >= MIN_HOURS * HOUR_MS;
  const inputClass =
    "h-7 w-full rounded border border-surface-600 bg-surface-950 px-1.5 text-[11px] text-surface-100 outline-none focus:border-accent-500 [color-scheme:dark]";
  return (
    <div className="border-surface-700 mt-1 flex flex-col gap-1.5 border-t px-2 pt-2">
      <div className="text-surface-500 text-[10px] font-medium tracking-wide uppercase">
        Custom range
      </div>
      <label className="text-surface-400 flex items-center gap-2 text-[11px]">
        <span className="w-8">From</span>
        <input
          type="datetime-local"
          step={3600}
          value={from}
          min={inputValue(spanStart)}
          max={inputValue(spanEnd)}
          onChange={(event) => setFrom(event.target.value)}
          className={inputClass}
        />
      </label>
      <label className="text-surface-400 flex items-center gap-2 text-[11px]">
        <span className="w-8">To</span>
        <input
          type="datetime-local"
          step={3600}
          value={to}
          min={inputValue(spanStart)}
          max={inputValue(spanEnd)}
          onChange={(event) => setTo(event.target.value)}
          className={inputClass}
        />
      </label>
      <button
        type="button"
        disabled={!valid}
        onClick={() => onApply({ start: iso(start), end: iso(end), label: rangeLabel(start, end) })}
        className="bg-accent-600 hover:bg-accent-500 focus-visible:ring-accent-300 h-7 self-end rounded px-3 text-[11px] font-medium text-white outline-none focus-visible:ring-1 disabled:opacity-40"
      >
        Apply
      </button>
      {!valid && (
        <span className="text-surface-500 text-[10px]">
          At least {MIN_HOURS} hours, inside the period.
        </span>
      )}
    </div>
  );
}
