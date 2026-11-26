import type { BlockContent, Report, ReportBlock } from "../data/reports";
import { findFreeSpot, pageMetrics, type PageMetrics } from "./report-layout";

// Putting a new block on a report: the first free spot, trying the roomier
// size first and the page the user is working on before the others.

/** Sizes in cells, biggest first; the first that fits is used. */
function preferredSizes(content: BlockContent): { w: number; h: number }[] {
  switch (content.kind) {
    case "widget":
      return [
        { w: 12, h: 9 },
        { w: 6, h: 8 },
        { w: 4, h: 6 },
        { w: 3, h: 4 },
      ];
    case "heading":
      return [
        { w: 12, h: 2 },
        { w: 6, h: 2 },
        { w: 4, h: 1 },
      ];
    case "text":
      return [
        { w: 12, h: 3 },
        { w: 6, h: 3 },
        { w: 4, h: 2 },
      ];
    case "divider":
      return [
        { w: 12, h: 1 },
        { w: 6, h: 1 },
      ];
    case "image":
      return [
        { w: 6, h: 6 },
        { w: 4, h: 4 },
        { w: 2, h: 2 },
      ];
    case "shape":
      return content.shape === "line"
        ? [
            { w: 12, h: 1 },
            { w: 6, h: 1 },
          ]
        : [
            { w: 4, h: 4 },
            { w: 3, h: 3 },
            { w: 2, h: 2 },
          ];
  }
}

/** Where `content` fits in the report, or null when no page has room. */
export function placeBlock(
  report: Report,
  content: BlockContent,
  preferredPageId: string | null,
): { pageId: string; block: ReportBlock } | null {
  const metrics = pageMetrics(report.page);
  const preferred = report.pages.find((page) => page.id === preferredPageId);
  const pages = preferred
    ? [preferred, ...report.pages.filter((page) => page !== preferred)]
    : report.pages;
  for (const page of pages) {
    for (const size of preferredSizes(content)) {
      const spot = findFreeSpot(size, page.blocks, metrics);
      if (spot)
        return {
          pageId: page.id,
          block: { id: crypto.randomUUID(), rect: { ...spot, ...size }, content },
        };
    }
  }
  return null;
}

/** The run result the report's latest widget uses: a sensible default for the next one. */
export function lastUsedResultId(report: Report): string | null {
  for (const page of [...report.pages].reverse()) {
    for (const block of [...page.blocks].reverse()) {
      if (block.content.kind === "widget") return block.content.resultId;
    }
  }
  return null;
}

/** A copy of the block in the first free spot of its page, or null when there's no room for one. */
export function duplicateBlock(
  block: ReportBlock,
  pageBlocks: ReportBlock[],
  metrics: PageMetrics,
): ReportBlock | null {
  const spot = findFreeSpot(block.rect, pageBlocks, metrics);
  if (!spot) return null;
  return { ...structuredClone(block), id: crypto.randomUUID(), rect: { ...block.rect, ...spot } };
}
