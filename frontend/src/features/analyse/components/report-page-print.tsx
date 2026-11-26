import { PAPER_SIZES, type PageSetup, type ReportPage } from "../data/reports";
import type { ReportTheme } from "../data/report-themes";
import { reportThemeStyle } from "../lib/report-theme";
import { blockBox, pageMetrics } from "../lib/report-layout";
import { ReportBlockView, type WidgetsStatus } from "./report-block-view";
import { ReportPageDecoration } from "./report-page-decoration";

const PX_PER_MM = 96 / 25.4;

/**
 * One page as it prints: the same page as in the editor, without the editing
 * frames, at the paper's real size in millimetres. The page is laid out at its
 * pixel size and scaled to the paper, so a page never spills onto a second
 * sheet over a fraction of a millimetre.
 */
export function ReportPagePrint({
  page,
  setup,
  theme,
  reportName,
  pageNumber,
  pageCount,
  widgets,
}: {
  page: ReportPage;
  setup: PageSetup;
  theme: ReportTheme;
  reportName: string;
  pageNumber: number;
  pageCount: number;
  widgets: WidgetsStatus;
}) {
  const metrics = pageMetrics(setup);
  const paper = PAPER_SIZES[setup.size];
  const [widthMm, heightMm] =
    setup.orientation === "portrait"
      ? [paper.widthMm, paper.heightMm]
      : [paper.heightMm, paper.widthMm];
  const scale = (widthMm * PX_PER_MM) / metrics.width;
  return (
    <div
      style={{
        width: `${widthMm}mm`,
        height: `${heightMm}mm`,
        overflow: "hidden",
        breakAfter: pageNumber < pageCount ? "page" : "auto",
        background: theme.background,
      }}
    >
      <div
        data-scheme={theme.scheme}
        style={{
          ...reportThemeStyle(theme),
          position: "relative",
          overflow: "hidden",
          width: metrics.width,
          height: metrics.height,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
        }}
      >
        <ReportPageDecoration
          theme={theme}
          width={metrics.width}
          height={metrics.height}
          reportName={reportName}
          pageNumber={pageNumber}
          pageCount={pageCount}
        />
        {page.blocks.map((block) => (
          <div key={block.id} style={{ position: "absolute", ...blockBox(block.rect, metrics) }}>
            <ReportBlockView block={block} widgets={widgets} theme={theme} />
          </div>
        ))}
      </div>
    </div>
  );
}
