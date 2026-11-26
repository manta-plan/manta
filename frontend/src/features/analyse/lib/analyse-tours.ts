import { useProjectStore } from "../../project/store/project-store";
import { startAfterRender } from "../../project/lib/workspace-tours";

function startReportBuilderTour() {
  // Starts on the Insert tab, whichever tab the panel was left on.
  document.querySelector<HTMLButtonElement>('[data-tour="report-tab-insert"]')?.click();
  startAfterRender([
    {
      element: '[data-tour="report-desk"]',
      popover: {
        title: "Pages",
        description:
          "Your report as paper pages, to scale. Click a block to select it, drag it to move it, drag a grip to resize it. Arrow keys nudge it (Shift resizes) and Delete removes it. Blocks snap to a grid and never overlap.",
        side: "left",
        align: "center",
      },
    },
    {
      element: '[data-tour="report-tab-insert"]',
      popover: {
        title: "Insert",
        description:
          "Add headings, text, images and shapes, or any widget from the built-in views and your own. Each widget shows the run result you choose, so one report can compare several.",
        side: "left",
        align: "start",
      },
    },
    {
      element: '[data-tour="report-tab-block"]',
      popover: {
        title: "Block settings",
        description:
          "Select a block to set its run result, title and exact position. A widget stays linked to its view; detach it to keep a copy that later edits and deletions there can’t change.",
        side: "left",
        align: "start",
      },
    },
    {
      element: '[data-tour="report-tab-theme"]',
      popover: {
        title: "Theme",
        description:
          "Colors, fonts, chart palette and card style, plus a header, footer with page numbers, backdrop and your logo. A report keeps its own theme, whatever the app’s theme is.",
        side: "left",
        align: "start",
      },
    },
    {
      element: '[data-tour="report-view-controls"]',
      popover: {
        title: "Undo, zoom and grid",
        description:
          "Undo and redo cover layout, content, theme and pages. Zoom the page, or show the grid blocks snap to.",
        side: "bottom",
        align: "end",
      },
    },
    {
      element: '[data-tour="report-export"]',
      popover: {
        title: "Export",
        description:
          "Opens the print dialog with the report at its paper size. Choose Save as PDF there.",
        side: "bottom",
        align: "end",
      },
    },
  ]);
}

/** Moves the app to `path` (wouter follows history.pushState). */
function goTo(path: string) {
  if (window.location.pathname !== path) window.history.pushState(null, "", path);
}

/** Resolves once `selector` is on the page (a page that loads data first), or after `timeoutMs` regardless. */
function waitFor(selector: string, timeoutMs = 15000): Promise<void> {
  return new Promise((resolve) => {
    const started = performance.now();
    const check = () =>
      document.querySelector(selector) || performance.now() - started > timeoutMs
        ? resolve()
        : window.setTimeout(check, 100);
    check();
  });
}

// Data → views → reports, as the home page describes them. The result and
// filter steps need a view open, so the tour opens System Overview for them
// and comes back home at the end.
export function startAnalyseWorkspaceTour() {
  if (useProjectStore.getState().selectedReportId) return startReportBuilderTour();
  const base =
    window.location.pathname.match(/^\/project\/[^/]+\/analyse/)?.[0] ?? window.location.pathname;
  const viewPath = `${base}/system-overview`;
  const openView = (next: () => void) => {
    goTo(viewPath);
    void waitFor('[data-tour="result-toolbar"]').then(next);
  };
  const openHome = (next: () => void) => {
    goTo(base);
    void waitFor('[data-tour="analyse-home"]').then(next);
  };
  startAfterRender([
    {
      element: '[data-tour="data-panel"]',
      popover: {
        title: "Data",
        description:
          "What there is to chart. Computed tables are ours, built from each solved result: open one for its SQL, assumptions and a preview. Raw tables are the result as the record stores it, to browse.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="views-panel"]',
      popover: {
        title: "Views",
        description:
          "Pages of widgets that chart the data: built-in ones first, then your own. + makes a new view; the search icon finds one. Next opens System Overview.",
        side: "right",
        align: "start",
        onNextClick: (_element, _step, { driver }) => openView(() => driver.moveNext()),
      },
    },
    {
      element: '[data-tour="result-toolbar"]',
      popover: {
        title: "Result and comparison",
        description:
          "Every view shows the result picked here. Compare with puts a second result beside it, on the same scale, and each widget can switch to the difference.",
        side: "bottom",
        align: "end",
        onPrevClick: (_element, _step, { driver }) => openHome(() => driver.movePrevious()),
      },
    },
    {
      element: '[data-tour="view-filters"]',
      popover: {
        title: "Filters",
        description:
          "Narrow a view to one investment period, some buses or some carriers. They apply to every widget that can use them, and are saved with the view.",
        side: "bottom",
        align: "end",
      },
    },
    {
      element: '[data-tour="reports-panel"]',
      popover: {
        title: "Reports",
        description:
          "Paper pages of widgets, text and key figures to print or share. + starts one from a template; each widget shows the result you choose.",
        side: "right",
        align: "start",
        onNextClick: (_element, _step, { driver }) => openHome(() => driver.moveNext()),
      },
    },
    {
      element: '[data-tour="analyse-home"]',
      popover: {
        title: "Back here",
        description:
          "This page: the results there are to analyse, a way into data, views and reports, and your own views and reports. Return to it with the Analyse tab.",
        side: "left",
        align: "center",
        onPrevClick: (_element, _step, { driver }) => openView(() => driver.movePrevious()),
      },
    },
  ]);
}
