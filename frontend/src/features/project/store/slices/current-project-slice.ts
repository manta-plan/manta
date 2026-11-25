// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { ProjectStoreSet } from "../types";

export function createCurrentProjectSlice(set: ProjectStoreSet) {
  return {
    // The project the workspace shows; what the runs, reports, inspections and
    // scenarios are saved under.
    currentProjectId: null as string | null,
    setCurrentProjectId: (id: string) => set({ currentProjectId: id }),

    isWelcomeDialogOpen: false,
    openWelcomeDialog: () => set({ isWelcomeDialogOpen: true }),
    closeWelcomeDialog: () => set({ isWelcomeDialogOpen: false }),
  };
}
