import { useEffect } from "react";
import { createPortal } from "react-dom";
import { PAPER_SIZES, type Report } from "../data/reports";
import { ReportPagePrint } from "./report-page-print";
import type { WidgetsStatus } from "./report-block-view";

const POLL_MS = 200;
// Charts and maps keep drawing for a moment after their data arrives.
const SETTLE_MS = 1500;
const GIVE_UP_MS = 25_000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Exports a report: renders its pages off-screen at paper size, waits for
 * every widget to finish loading, then opens the browser's print dialog,
 * where "Save as PDF" makes the file. The print stylesheet (index.css)
 * hides the app and prints these pages alone. `onDone` runs once the dialog
 * closes, which removes the pages again.
 */
export function ReportPrintRoot({
  report,
  widgets,
  onDone,
}: {
  report: Report;
  widgets: WidgetsStatus;
  onDone: () => void;
}) {
  useEffect(() => {
    let isCancelled = false;
    void (async () => {
      const started = Date.now();
      await sleep(POLL_MS);
      // A loading widget shows a skeleton, or a thin bar while it refreshes; both are status regions.
      while (
        !isCancelled &&
        Date.now() - started < GIVE_UP_MS &&
        document.querySelector('#report-print-root [role="status"]')
      )
        await sleep(POLL_MS);
      await sleep(SETTLE_MS);
      if (!isCancelled) window.print();
    })();
    window.addEventListener("afterprint", onDone);
    return () => {
      isCancelled = true;
      window.removeEventListener("afterprint", onDone);
    };
  }, [onDone]);

  const paper = PAPER_SIZES[report.page.size];
  const [widthMm, heightMm] =
    report.page.orientation === "portrait"
      ? [paper.widthMm, paper.heightMm]
      : [paper.heightMm, paper.widthMm];
  return createPortal(
    <div id="report-print-root">
      <style>{`@page { size: ${widthMm}mm ${heightMm}mm; margin: 0 }`}</style>
      {report.pages.map((page, index) => (
        <ReportPagePrint
          key={page.id}
          page={page}
          setup={report.page}
          theme={report.theme}
          reportName={report.name}
          pageNumber={index + 1}
          pageCount={report.pages.length}
          widgets={widgets}
        />
      ))}
    </div>,
    document.body,
  );
}
