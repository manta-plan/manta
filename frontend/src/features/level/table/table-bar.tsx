// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { LuFilter, LuMap, LuMapPin, LuX } from "react-icons/lu";
import { useLevelStore } from "../level-store";
import { FullscreenButton } from "../fullscreen/fullscreen-button";
import { useInFullscreen } from "../fullscreen/fullscreen-context";

// The bar over the table: its title, what narrows it (locations picked on
// the map, column filters; each chip clears its own), the column picker and
// the full screen button, the column picker and the "Map & graph" toggle
// (not in the full screen dialog).

const chip =
  "flex h-6 shrink-0 items-center gap-1 rounded-full border border-accent-500 bg-accent-600/15 px-2 text-[11px] text-accent-200 outline-none hover:bg-accent-600/25 focus-visible:ring-1 focus-visible:ring-accent-500";

export function TableBar({
  title,
  picker,
  filterCount = 0,
  children,
}: {
  title: string;
  picker?: ReactNode;
  filterCount?: number;
  /** More controls before the picker (the entity's "Filter attributes"). */ children?: ReactNode;
}) {
  const locations = useLevelStore((s) => s.selectedLocations);
  const setLocations = useLevelStore((s) => s.setSelectedLocations);
  const filters = useLevelStore((s) => s.columnFilters);
  const setFilter = useLevelStore((s) => s.setColumnFilter);
  const isSideOpen = useLevelStore((s) => s.isMapGraphOpen);
  const setSideOpen = useLevelStore((s) => s.setMapGraphOpen);
  const inDialog = useInFullscreen();
  return (
    <div className="border-surface-700 flex h-10 shrink-0 items-center gap-2 border-b px-3">
      <h2 className="text-surface-100 shrink-0 text-[12px] font-medium">{title}</h2>
      {locations.length > 0 && (
        <button
          type="button"
          onClick={() => setLocations([])}
          title={`Showing ${locations.join(", ")}. Clear the map selection`}
          className={chip}
        >
          <LuMapPin size={11} />
          {locations.length} {locations.length === 1 ? "location" : "locations"}
          <LuX size={11} />
        </button>
      )}
      {filterCount > 0 && (
        <button
          type="button"
          onClick={() => Object.keys(filters).forEach((key) => setFilter(key, null))}
          title="Remove all column filters"
          className={chip}
        >
          <LuFilter size={11} />
          {filterCount} column {filterCount === 1 ? "filter" : "filters"}
          <LuX size={11} />
        </button>
      )}
      <span className="min-w-0 flex-1" />
      {children}
      <FullscreenButton block="table" />
      {picker}
      {!inDialog && (
        <button
          type="button"
          aria-pressed={isSideOpen}
          onClick={() => setSideOpen(!isSideOpen)}
          title={isSideOpen ? "Hide the map and graph" : "Show the map and graph"}
          className={`focus-visible:border-accent-500 flex h-7 shrink-0 items-center gap-1.5 rounded border px-2 text-[12px] outline-none ${
            isSideOpen
              ? "border-accent-500 bg-accent-600/15 text-accent-200"
              : "border-surface-600 text-surface-300 hover:border-surface-500 hover:text-surface-100"
          }`}
        >
          <LuMap size={13} />
          Map &amp; graph
        </button>
      )}
    </div>
  );
}
