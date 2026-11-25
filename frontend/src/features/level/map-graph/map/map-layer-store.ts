// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { create } from "zustand";

// What the map draws, from its "Map layers" popover. Kept across levels for
// the session.

export type RegionShading =
  | "generator-capacity"
  | "generator-utilisation"
  | "load-peak"
  | "load-demand"
  | "storage-volume"
  | "storage-utilisation"
  | "link-capacity"
  | "link-utilisation"
  | "bus-price";

export type LineColouring = "capacity" | "loading";

export interface LayerOption<T extends string> {
  id: T;
  label: string;
  /** Read from run results: only on Inspect. */
  needsResults?: boolean;
}

export const REGION_SHADING_ROWS: { row: string; options: LayerOption<RegionShading>[] }[] = [
  {
    row: "Generator",
    options: [
      { id: "generator-capacity", label: "Capacity" },
      { id: "generator-utilisation", label: "Utilisation", needsResults: true },
    ],
  },
  {
    row: "Load",
    options: [
      { id: "load-peak", label: "Peak load" },
      { id: "load-demand", label: "Annual demand" },
    ],
  },
  {
    row: "Storage",
    options: [
      { id: "storage-volume", label: "Volume" },
      { id: "storage-utilisation", label: "Utilisation", needsResults: true },
    ],
  },
  {
    row: "Link",
    options: [
      { id: "link-capacity", label: "Capacity" },
      { id: "link-utilisation", label: "Utilisation", needsResults: true },
    ],
  },
  { row: "Bus", options: [{ id: "bus-price", label: "Mean price", needsResults: true }] },
];

export const LINE_COLOURING_OPTIONS: LayerOption<LineColouring>[] = [
  { id: "capacity", label: "Capacity" },
  { id: "loading", label: "Loading", needsResults: true },
];

export function regionShadingLabel(id: RegionShading): string {
  for (const { row, options } of REGION_SHADING_ROWS) {
    const option = options.find((item) => item.id === id);
    if (option) return `${row} · ${option.label}`;
  }
  return id;
}

export const needsResults = (id: RegionShading | LineColouring): boolean =>
  [...REGION_SHADING_ROWS.flatMap((row) => row.options), ...LINE_COLOURING_OPTIONS].some(
    (option) => option.id === id && option.needsResults,
  );

interface MapLayerState {
  showTopology: boolean;
  setShowTopology: (show: boolean) => void;
  showSiting: boolean;
  setShowSiting: (show: boolean) => void;
  regionShading: RegionShading | null;
  setRegionShading: (shading: RegionShading | null) => void;
  lineColouring: LineColouring | null;
  setLineColouring: (colouring: LineColouring | null) => void;
  /** Plain drag selects locations (instead of panning). */
  isSelecting: boolean;
  setSelecting: (selecting: boolean) => void;
}

export const useMapLayerStore = create<MapLayerState>((set) => ({
  showTopology: true,
  setShowTopology: (showTopology) => set({ showTopology }),
  showSiting: true,
  setShowSiting: (showSiting) => set({ showSiting }),
  regionShading: null,
  setRegionShading: (regionShading) => set({ regionShading }),
  lineColouring: null,
  setLineColouring: (lineColouring) => set({ lineColouring }),
  isSelecting: false,
  setSelecting: (isSelecting) => set({ isSelecting }),
}));

/** The ramp's colour at t (0 to 1): blue to orange. */
export const rampColor = (t: number) => `hsl(${210 - 190 * Math.max(0, Math.min(1, t))}, 70%, 55%)`;
export const RAMP_GRADIENT = `linear-gradient(to right, ${[0, 0.25, 0.5, 0.75, 1].map(rampColor).join(", ")})`;
