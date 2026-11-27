// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { AddButton, FilterButton } from "../../project/components/sidebar-actions";
import { useProjectStore } from "../../project/store/project-store";
import { useRunsStore } from "../store/runs-store";
import { useOpenNewRun } from "../use-open-new-run";

// The buttons in the Runs panel's header: the filter panel and a new run.
export function RunsPanelActions() {
  const isRunFilterDrawerOpen = useProjectStore((s) => s.isRunFilterDrawerOpen);
  const openRunFilterDrawer = useProjectStore((s) => s.openRunFilterDrawer);
  const closeRunFilterDrawer = useProjectStore((s) => s.closeRunFilterDrawer);
  const closeNewRunDrawer = useProjectStore((s) => s.closeNewRunDrawer);
  const hasStatusFilter = useRunsStore((s) => s.selectedStatuses.length > 0);
  const openNewRun = useOpenNewRun();

  function toggleFilters() {
    if (isRunFilterDrawerOpen) {
      closeRunFilterDrawer();
      return;
    }

    // Both panels sit on the left edge.
    closeNewRunDrawer();
    openRunFilterDrawer();
  }

  return (
    <div className="flex items-center gap-2">
      <FilterButton
        isActive={isRunFilterDrawerOpen || hasStatusFilter}
        label="Filter runs"
        onClick={toggleFilters}
      />
      <AddButton label="New Run" onClick={() => openNewRun()} />
    </div>
  );
}
