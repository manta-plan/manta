// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { driver, type DriveStep } from "driver.js";
import { useProjectStore } from "../store/project-store";

function openScenarioDisclosure(tourId: string) {
  const disclosure = document.querySelector<HTMLButtonElement>(`[data-tour="${tourId}"]`);
  if (disclosure?.getAttribute("aria-expanded") === "false") disclosure.click();
}

export function startAfterRender(steps: DriveStep[], onDestroyed?: () => void) {
  window.requestAnimationFrame(() => {
    driver({
      animate: true,
      overlayColor: "#05070b",
      overlayOpacity: 0.7,
      stagePadding: 6,
      stageRadius: 4,
      showProgress: true,
      progressText: "{{current}} of {{total}}",
      nextBtnText: "Next",
      prevBtnText: "Back",
      doneBtnText: "Done",
      popoverClass: "manta-driver-popover",
      steps,
      onDestroyed,
    }).drive();
  });
}

// Written for a first-time visitor right after login: nothing is imported
// yet, so it points at the sidebar (present on every home route) and
// walks the catalogue → project → playbook order rather than any one page.
export function startHomeTour() {
  startAfterRender([
    {
      element: '[data-tour="home-nav"]',
      popover: {
        title: "Welcome to MantaPlan",
        description:
          "Everything outside a project lives here. Use this sidebar to move between your projects, data, playbooks, and compute.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="home-nav-data"]',
      popover: {
        title: "Start with data",
        description:
          "Import a model package into the data catalogue first. Every project is created from a package stored here.",
        side: "right",
        align: "center",
      },
    },
    {
      element: '[data-tour="home-nav-projects"]',
      popover: {
        title: "Projects",
        description:
          "Create a project from an imported package, then open it to edit scenarios, run them, and review the results.",
        side: "right",
        align: "center",
      },
    },
    {
      element: '[data-tour="home-nav-playbooks"]',
      popover: {
        title: "Playbooks",
        description:
          "Reusable run recipes. Browse them here, and use a compatible one to prefill a run inside a project.",
        side: "right",
        align: "center",
      },
    },
    {
      element: '[data-tour="home-nav-infrastructure"]',
      popover: {
        title: "Infrastructure",
        description: "The cloud resources your runs execute on.",
        side: "right",
        align: "center",
      },
    },
    {
      element: '[data-tour="home-documentation"]',
      popover: {
        title: "Documentation",
        description:
          "Guides and reference material. Restart this tour from the header at any time.",
        side: "bottom",
        align: "end",
      },
    },
  ]);
}

export function startBuildWorkspaceTour() {
  startAfterRender([
    {
      element: '[data-tour="scenarios-panel"]',
      popover: {
        title: "Scenarios",
        description:
          "The record's scenarios and what each one changes. Click one to show it: the tree and the page follow.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="record-tree-panel"]',
      popover: {
        title: "Record",
        description:
          "Entities by type and carrier, and locations with their buses. Click a row to open its page.",
        side: "right",
        align: "center",
      },
    },
    {
      element: '[data-tour="inspect-main-section"]',
      popover: {
        title: "Level page",
        description:
          "Stat tiles, the table, the map and graph, and the chart drawer, for the level the tree opened. The investment period and time window above set what they read.",
        side: "left",
        align: "center",
      },
    },
  ]);
}

export function startRunWorkspaceTour() {
  openScenarioDisclosure("scenario-disclosure");
  // The "Select a run" step needs a real row to point at — when the
  // project has none yet, show a non-interactive example row for the
  // tour's duration instead (see RunsPanel), and clean it up when the
  // tour ends (Done, close, or Escape all fire onDestroyed).
  const hasRealRunItem = Boolean(document.querySelector('[data-tour="run-item"]'));
  if (!hasRealRunItem) useProjectStore.getState().setRunTourPlaceholderVisible(true);
  startAfterRender(
    [
      {
        element: '[data-tour="runs-panel"]',
        popover: {
          title: "Runs",
          description:
            "This panel lists every run in the project, with its current execution status.",
          side: "right",
          align: "start",
        },
      },
      {
        element: '[data-tour="new-run-action"]',
        popover: {
          title: "Create a run",
          description: "Use this action to open the run configuration form.",
          side: "right",
          align: "start",
        },
      },
      {
        element: '[data-tour="run-item"]',
        popover: {
          title: "Select a run",
          description:
            "Select a row to inspect its flow, inputs, logs, and outputs. Select it again to return here.",
          side: "right",
          align: "center",
        },
      },
      {
        element: '[data-tour="run-main-section"]',
        popover: {
          title: "Run workspace",
          description:
            "This area shows the selected run. When no run is selected, it provides this overview and tour.",
          side: "left",
          align: "center",
        },
      },
      {
        element: '[data-tour="scenario-playbooks-panel"]',
        popover: {
          title: "Playbooks by scenario",
          description: "Choose a scenario here. Its compatible playbooks appear beneath it.",
          side: "right",
          align: "start",
        },
      },
      {
        element: '[data-tour="playbook-item"]',
        popover: {
          title: "Prepare a playbook",
          description:
            "Select a compatible playbook to prefill the new-run form with that scenario and playbook.",
          side: "right",
          align: "center",
        },
      },
    ],
    hasRealRunItem
      ? undefined
      : () => useProjectStore.getState().setRunTourPlaceholderVisible(false),
  );
}

export function startInspectWorkspaceTour() {
  // Built-in inspections are always listed, so there's always an item to point at.
  startAfterRender([
    {
      element: '[data-tour="inspections-panel"]',
      popover: {
        title: "Inspections",
        description: "Built-in inspections come first, then your own.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="new-inspection-action"]',
      popover: {
        title: "Create an inspection",
        description: "Start from a blank page, a built-in inspection or one of your own.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="inspection-item"]',
      popover: {
        title: "Open an inspection",
        description: "Select an inspection to open its widgets. Select it again to return here.",
        side: "right",
        align: "center",
      },
    },
    {
      element: '[data-tour="inspect-main-section"]',
      popover: {
        title: "Inspect workspace",
        description:
          "Pick a result, compare and filter, then add or remove widgets. Your own inspections save as you go; a built-in one can be saved as yours.",
        side: "left",
        align: "center",
      },
    },
  ]);
}
