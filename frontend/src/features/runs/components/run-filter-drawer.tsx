// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { LuListFilter, LuX } from "react-icons/lu";
import { useProjectStore } from "../../project/store/project-store";
import { statusOptions } from "../status";
import { draftStatus } from "../status-groups";
import { useRunsStore } from "../store/runs-store";

const filterOptions = [...statusOptions, { label: "Draft", value: draftStatus }];

// Left overlay with the status filter. It writes the shared selection, so the backend is asked
// for the selected states and the sidebar, the stats and the table all follow.
export function RunFilterDrawer() {
  const isOpen = useProjectStore((s) => s.isRunFilterDrawerOpen);
  const closeRunFilterDrawer = useProjectStore((s) => s.closeRunFilterDrawer);
  const selectedStatuses = useRunsStore((s) => s.selectedStatuses);
  const setSelectedStatuses = useRunsStore((s) => s.setSelectedStatuses);

  function toggle(value: string) {
    void setSelectedStatuses(
      selectedStatuses.includes(value)
        ? selectedStatuses.filter((status) => status !== value)
        : [...selectedStatuses, value],
    );
  }

  return (
    <aside
      aria-hidden={!isOpen}
      aria-label="Run filters"
      className={`border-surface-600/60 bg-surface-800/70 absolute top-0 left-0 z-20 flex h-full w-72 flex-col border-r backdrop-blur-xl transition-transform duration-200 ease-out ${
        isOpen ? "pointer-events-auto translate-x-0" : "pointer-events-none -translate-x-full"
      }`}
      inert={!isOpen}
    >
      <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
        <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          <LuListFilter size={12} aria-hidden="true" />
          Run Filters
        </div>
        <button
          aria-label="Close run filters"
          className="text-surface-400 hover:text-surface-100 outline-none"
          onClick={closeRunFilterDrawer}
          type="button"
        >
          <LuX size={14} aria-hidden="true" />
        </button>
      </div>
      <fieldset className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
        <legend className="text-surface-400 mb-1 text-[11px] font-medium">Status</legend>
        {filterOptions.map((option) => (
          <label
            className="text-surface-200 hover:bg-surface-700 flex h-8 cursor-pointer items-center gap-2 rounded px-2 text-[12px]"
            key={option.value}
          >
            <input
              checked={selectedStatuses.includes(option.value)}
              className="accent-accent-500 h-3.5 w-3.5"
              onChange={() => toggle(option.value)}
              type="checkbox"
            />
            {option.label}
          </label>
        ))}
      </fieldset>
      <div className="border-surface-600/60 shrink-0 border-t p-3">
        <button
          className="border-surface-600 text-surface-200 hover:bg-surface-700 w-full rounded border px-3 py-1.5 text-[12px] font-medium outline-none disabled:cursor-not-allowed disabled:opacity-45"
          disabled={selectedStatuses.length === 0}
          onClick={() => void setSelectedStatuses([])}
          title={selectedStatuses.length === 0 ? "No filter is set" : undefined}
          type="button"
        >
          Clear Filters
        </button>
      </div>
    </aside>
  );
}
