import type { BlockContent, PageSetup, ReportBlock, ReportPage } from "./reports";
import { MIN_WIDGET_ROWS, pageMetrics } from "../lib/report-layout";

// Starting layouts for a new report. A template is a few bands of blocks,
// stacked down the page; a band is either a fixed number of rows or shares
// what's left with the other flexible bands. Laying them out from the page's
// row count keeps a template sensible on every paper and orientation.

export interface TemplateContext {
  /** The report's name, for its title. */
  name: string;
  portrait: boolean;
  /** Two of the record's run results; the same one twice if it has only one. */
  results: [{ id: string; label: string }, { id: string; label: string }];
}

interface BandItem {
  cols: number;
  content: BlockContent;
}

interface Band {
  rows: number | { flex: number };
  items: BandItem[];
}

export interface ReportTemplate {
  id: string;
  name: string;
  description: string;
  /** Whether it places widgets, which need a run result to show. */
  needsResults: boolean;
  pages: (context: TemplateContext) => Band[][];
}

const widget = (widgetId: string, resultId: string, cols: number): BandItem => ({
  cols,
  content: { kind: "widget", ref: { source: "built-in", widgetId }, resultId },
});
const heading = (text: string, level: 1 | 2 | 3, cols = 12): BandItem => ({
  cols,
  content: { kind: "heading", text, level },
});
const text = (body: string, cols = 12): BandItem => ({
  cols,
  content: { kind: "text", text: body },
});
const divider = (): BandItem => ({ cols: 12, content: { kind: "divider" } });

const SUMMARY_PROMPT = "Summarise the findings here. **Markdown** works: lists, bold, links.";

export const REPORT_TEMPLATES: ReportTemplate[] = [
  {
    id: "blank",
    name: "Blank",
    description: "An empty page",
    needsResults: false,
    pages: () => [[]],
  },
  {
    id: "summary",
    name: "One-page summary",
    description: "Title, a short summary and three charts",
    needsResults: true,
    pages: ({ name, portrait, results: [a] }) => [
      [
        { rows: 2, items: [heading(name, 1)] },
        { rows: portrait ? 3 : 2, items: [text(SUMMARY_PROMPT)] },
        {
          rows: { flex: 1 },
          items: [widget("generator-supply", a.id, 6), widget("cost-by-component", a.id, 6)],
        },
        { rows: { flex: 1 }, items: [widget("dispatch-stack", a.id, 12)] },
      ],
    ],
  },
  {
    id: "comparison",
    name: "Two-result comparison",
    description: "Two run results side by side",
    needsResults: true,
    pages: ({ name, portrait, results: [a, b] }) => [
      [
        // No result headings: each widget's title names its result, and stays right when it changes.
        { rows: 2, items: [heading(name, 1)] },
        {
          rows: { flex: 1 },
          items: [widget("generator-supply", a.id, 6), widget("generator-supply", b.id, 6)],
        },
        {
          rows: { flex: 1 },
          items: [widget("dispatch-stack", a.id, 6), widget("dispatch-stack", b.id, 6)],
        },
        {
          rows: portrait ? 3 : 2,
          items: [text("What changed between the two results? **Markdown** works.")],
        },
      ],
    ],
  },
  {
    id: "overview-costs",
    name: "Overview and costs",
    description: "Two pages: the system, then where the money goes",
    needsResults: true,
    pages: ({ name, portrait, results: [a] }) => [
      [
        { rows: 2, items: [heading(name, 1)] },
        { rows: portrait ? 3 : 2, items: [text(SUMMARY_PROMPT)] },
        { rows: { flex: 1 }, items: [widget("generator-supply", a.id, 12)] },
        {
          rows: { flex: 1 },
          items: [widget("bus-price-map", a.id, 6), widget("withdrawal", a.id, 6)],
        },
      ],
      [
        { rows: 2, items: [heading("System costs", 2)] },
        { rows: 1, items: [divider()] },
        {
          rows: { flex: 1 },
          items: [widget("cost-by-component", a.id, 6), widget("cost-by-carrier", a.id, 6)],
        },
        { rows: { flex: 1 }, items: [widget("installed-capacity", a.id, 12)] },
      ],
    ],
  },
  {
    id: "dispatch",
    name: "Dispatch deep dive",
    description: "A large dispatch chart with curtailment and prices",
    needsResults: true,
    pages: ({ name, portrait, results: [a] }) => [
      [
        { rows: 2, items: [heading(name, 1)] },
        {
          rows: portrait ? 3 : 2,
          items: [text("What drives dispatch in this result? **Markdown** works.")],
        },
        { rows: { flex: 2 }, items: [widget("dispatch-stack", a.id, 12)] },
        {
          rows: { flex: 1 },
          items: [widget("curtailment", a.id, 6), widget("bus-price-map", a.id, 6)],
        },
      ],
    ],
  },
];

export function reportTemplate(id: string): ReportTemplate {
  return REPORT_TEMPLATES.find((template) => template.id === id) ?? REPORT_TEMPLATES[0];
}

/** The rows each band gets: fixed ones as asked, flexible ones sharing the rest and never below a widget's minimum. */
function bandRows(bands: Band[], totalRows: number): number[] {
  const fixed = bands.reduce(
    (sum, band) => sum + (typeof band.rows === "number" ? band.rows : 0),
    0,
  );
  const flexTotal = bands.reduce(
    (sum, band) => sum + (typeof band.rows === "number" ? 0 : band.rows.flex),
    0,
  );
  const spare = Math.max(0, totalRows - fixed);
  const flexBands = bands.filter((band) => typeof band.rows !== "number");
  const last = flexBands[flexBands.length - 1];
  let given = 0;
  return bands.map((band) => {
    if (typeof band.rows === "number") return band.rows;
    // The last flexible band takes the rounding left over.
    const rows = band === last ? spare - given : Math.floor((spare * band.rows.flex) / flexTotal);
    given += rows;
    return Math.max(MIN_WIDGET_ROWS, rows);
  });
}

/** A template's pages for this paper, with new ids. */
export function buildTemplatePages(
  template: ReportTemplate,
  setup: PageSetup,
  context: Omit<TemplateContext, "portrait">,
): ReportPage[] {
  const { rows } = pageMetrics(setup);
  return template.pages({ ...context, portrait: setup.orientation === "portrait" }).map((bands) => {
    const heights = bandRows(bands, rows);
    const blocks: ReportBlock[] = [];
    let y = 0;
    bands.forEach((band, index) => {
      let x = 0;
      for (const item of band.items) {
        blocks.push({
          id: crypto.randomUUID(),
          rect: { x, y, w: item.cols, h: heights[index] },
          content: item.content,
        });
        x += item.cols;
      }
      y += heights[index];
    });
    return { id: crypto.randomUUID(), blocks };
  });
}
