// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useProjectStore } from "../project/store/project-store";
import { useRunsStore } from "./store/runs-store";

/**
 * Opens the New Run panel with a fresh form, optionally with a scenario and a playbook
 * picked. The filter panel shares the left edge, so it closes.
 */
export function useOpenNewRun() {
  const prepareNewRun = useRunsStore((s) => s.prepareNewRun);
  const openNewRunDrawer = useProjectStore((s) => s.openNewRunDrawer);
  const closeRunFilterDrawer = useProjectStore((s) => s.closeRunFilterDrawer);

  return (selection?: { scenario?: string | null; playbook?: string | null }) => {
    prepareNewRun(selection);
    closeRunFilterDrawer();
    openNewRunDrawer();
  };
}
