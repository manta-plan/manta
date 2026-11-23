// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { createContext, useContext } from "react";

/** The blocks of a level page that open full screen. */
export type ExpandableBlock = "table" | "map-graph" | "chart";

export const BLOCK_LABELS: Record<ExpandableBlock, string> = {
  table: "Table",
  "map-graph": "Map & graph",
  chart: "Chart drawer",
};

/** Whether the block at hand is the one in the full screen dialog. */
export const InFullscreen = createContext(false);

/** Whether this block is in the full screen dialog (its bar then offers Exit, and drops controls that only make sense in place). */
export function useInFullscreen() {
  return useContext(InFullscreen);
}
