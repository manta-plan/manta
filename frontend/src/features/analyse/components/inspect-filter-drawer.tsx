import { useState, type ReactNode } from "react";
import clsx from "clsx";
import { LuCheck, LuListFilter, LuSearch, LuX } from "react-icons/lu";
import {
  CARRIER_GROUPS,
  EMPTY_FILTERS,
  activeDimensions,
  describePeriod,
  type InspectFilters,
} from "../lib/inspect-filters";

// Only the first matches are listed; search narrows the rest.
const BUS_LIST_LIMIT = 200;

function Section({
  title,
  detail,
  onClear,
  children,
}: {
  title: string;
  detail: string;
  onClear?: () => void;
  children: ReactNode;
}) {
  return (
    <section className="border-surface-600/60 flex flex-col gap-2 border-b p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-surface-300 text-[11px] font-semibold tracking-wide uppercase">
          {title}
        </div>
        <div className="text-surface-500 flex items-center gap-2 text-[11px]">
          {detail}
          {onClear && (
            <button
              type="button"
              onClick={onClear}
              className="text-accent-400 hover:text-accent-300 outline-none"
            >
              Clear
            </button>
          )}
        </div>
      </div>
      {children}
    </section>
  );
}

const inputClassName =
  "h-8 rounded border border-surface-600 bg-surface-900 px-2 text-[12px] text-surface-50 outline-none focus:border-accent-500";

// One investment period, or all of them: energies and costs are per period.
function PeriodSection({
  value,
  periods,
  onChange,
}: {
  value: string | null;
  periods: string[];
  onChange: (value: string | null) => void;
}) {
  const options: (string | null)[] = [null, ...periods];
  return (
    <Section
      title="Period"
      detail={describePeriod(value)}
      onClear={value !== null ? () => onChange(null) : undefined}
    >
      <div className="flex flex-wrap gap-1">
        {options.map((period) => {
          const isActive = period === value;
          return (
            <button
              key={period ?? "all"}
              type="button"
              aria-pressed={isActive}
              onClick={() => onChange(period)}
              className={clsx(
                "rounded border px-2 py-0.5 text-[11px] outline-none",
                isActive
                  ? "border-accent-500 bg-accent-600/20 text-surface-50"
                  : "border-surface-600 text-surface-300 hover:border-surface-500 hover:text-surface-100",
              )}
            >
              {period ?? "All"}
            </button>
          );
        })}
      </div>
    </Section>
  );
}

function BusSection({
  value,
  allBuses,
  onChange,
}: {
  value: string[];
  allBuses: string[];
  onChange: (value: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const selected = new Set(value);
  const matches = allBuses.filter((bus) => bus.toLowerCase().includes(query.trim().toLowerCase()));
  // Selected buses first, so they stay in reach while searching.
  const listed = [
    ...matches.filter((bus) => selected.has(bus)),
    ...matches.filter((bus) => !selected.has(bus)),
  ].slice(0, BUS_LIST_LIMIT);

  const toggle = (bus: string) =>
    onChange(selected.has(bus) ? value.filter((item) => item !== bus) : [...value, bus]);

  return (
    <Section
      title="Buses"
      detail={
        value.length > 0 ? `${value.length} of ${allBuses.length}` : `${allBuses.length} buses`
      }
      onClear={value.length > 0 ? () => onChange([]) : undefined}
    >
      {allBuses.length === 0 ? (
        <div className="text-surface-500 text-[12px]">No buses loaded for this project.</div>
      ) : (
        <>
          <div className="relative">
            <LuSearch
              size={12}
              className="text-surface-500 pointer-events-none absolute top-1/2 left-2 -translate-y-1/2"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search buses"
              className={clsx(inputClassName, "w-full pl-7")}
            />
          </div>
          {query.trim() && matches.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([...new Set([...value, ...matches])])}
              className="text-accent-400 hover:text-accent-300 self-start text-[11px] outline-none"
            >
              Select all {matches.length} matches
            </button>
          )}
          <div className="border-surface-600 bg-surface-900 max-h-56 overflow-y-auto rounded border">
            {listed.map((bus) => (
              <button
                key={bus}
                type="button"
                role="checkbox"
                aria-checked={selected.has(bus)}
                onClick={() => toggle(bus)}
                className="text-surface-200 hover:bg-surface-700/60 focus-visible:bg-surface-700/60 flex w-full items-center gap-2 px-2 py-1 text-left text-[12px] outline-none"
              >
                <span
                  className={clsx(
                    "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border",
                    selected.has(bus)
                      ? "border-accent-500 bg-accent-600 text-white"
                      : "border-surface-500",
                  )}
                >
                  {selected.has(bus) && <LuCheck size={10} />}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono text-[11px]">{bus}</span>
              </button>
            ))}
            {matches.length === 0 && (
              <div className="text-surface-500 px-2 py-1.5 text-[12px]">No buses match.</div>
            )}
            {matches.length > BUS_LIST_LIMIT && (
              <div className="text-surface-500 px-2 py-1.5 text-[11px]">
                {matches.length - BUS_LIST_LIMIT} more — search to narrow.
              </div>
            )}
          </div>
        </>
      )}
    </Section>
  );
}

function CarrierSection({
  value,
  onChange,
}: {
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const toggle = (id: string) =>
    onChange(value.includes(id) ? value.filter((item) => item !== id) : [...value, id]);

  return (
    <Section
      title="Carriers"
      detail={value.length > 0 ? `${value.length} of ${CARRIER_GROUPS.length}` : "All carriers"}
      onClear={value.length > 0 ? () => onChange([]) : undefined}
    >
      <div className="flex flex-wrap gap-1">
        {CARRIER_GROUPS.map((group) => {
          const isActive = value.includes(group.id);
          return (
            <button
              key={group.id}
              type="button"
              aria-pressed={isActive}
              onClick={() => toggle(group.id)}
              className={clsx(
                "flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] outline-none",
                isActive
                  ? "border-accent-500 bg-accent-600/20 text-surface-50"
                  : "border-surface-600 text-surface-300 hover:border-surface-500 hover:text-surface-100",
              )}
            >
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: group.color }} />
              {group.label}
            </button>
          );
        })}
      </div>
    </Section>
  );
}

// The inspect page's own right drawer, layered over the whole page,
// header included. Changes apply as they're made.
export function InspectFilterDrawer({
  isOpen,
  onClose,
  filters,
  onChange,
  allBuses,
  periods,
}: {
  isOpen: boolean;
  onClose: () => void;
  filters: InspectFilters;
  onChange: (filters: InspectFilters) => void;
  allBuses: string[];
  periods: string[];
}) {
  const hasFilters = activeDimensions(filters).length > 0;

  return (
    <aside
      aria-hidden={!isOpen}
      inert={!isOpen}
      className={clsx(
        "absolute top-0 right-0 z-20 flex h-full w-80 flex-col border-l border-surface-600/60 bg-surface-800/80 backdrop-blur-xl transition-transform duration-200 ease-out",
        isOpen ? "pointer-events-auto translate-x-0" : "pointer-events-none translate-x-full",
      )}
    >
      <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
        <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          <LuListFilter size={12} />
          Filters
        </div>
        <div className="flex items-center gap-3">
          {hasFilters && (
            <button
              type="button"
              onClick={() => onChange(EMPTY_FILTERS)}
              className="text-accent-400 hover:text-accent-300 text-[11px] outline-none"
            >
              Reset all
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className="text-surface-400 hover:text-surface-100 outline-none"
          >
            <LuX size={14} />
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="border-surface-600/60 text-surface-400 border-b px-3 py-2 text-[11px] leading-4">
          Applies to every widget in this view, and is saved with it. Widgets that can't use a
          filter say so.
        </p>
        <PeriodSection
          value={filters.period}
          periods={periods}
          onChange={(period) => onChange({ ...filters, period })}
        />
        <BusSection
          value={filters.buses}
          allBuses={allBuses}
          onChange={(buses) => onChange({ ...filters, buses })}
        />
        <CarrierSection
          value={filters.carriers}
          onChange={(carriers) => onChange({ ...filters, carriers })}
        />
      </div>
    </aside>
  );
}
