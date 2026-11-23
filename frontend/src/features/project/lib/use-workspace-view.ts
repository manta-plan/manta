// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useLocation } from "wouter";
import { useLevelStore } from "../../level/level-store";
import { getActiveProjectTab } from "./project-route";

// Build and Inspect show one page per level, the map in Map & graph (see
// features/level). The map is shown when that block is open on its Map tab.

export interface WorkspaceViewState {
  /** Whether the map is what's shown. */
  isMapShown: boolean;
}

export function useWorkspaceView(): WorkspaceViewState {
  const [location] = useLocation();
  const tab = getActiveProjectTab(location);
  const isMapShown = useLevelStore((s) => s.isMapGraphOpen && s.mapGraphTab === "map");
  return { isMapShown: (tab === "build" || tab === "inspect") && isMapShown };
}
