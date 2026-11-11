import { driver, type DriveStep } from "driver.js";

function startAfterRender(steps: DriveStep[]) {
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
    }).drive();
  });
}

// Written for a first-time visitor right after login: it points at the
// sidebar, which is present on every home route.
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
  ]);
}
