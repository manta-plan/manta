import {
  PAPER_SIZES,
  type BlockContent,
  type BlockRect,
  type PageSetup,
  type ReportBlock,
  type ReportPage,
} from "../data/reports";

// The grid a report page is laid out on. Blocks sit on whole cells: 12
// columns across the page's margins, and rows half a column tall, so a text
// line or a heading needs one row and a chart a handful.

export const GRID_COLUMNS = 12;
export const PAGE_MARGIN = 48;
/** Space kept around each block inside its cells, so neighbours never touch. */
export const BLOCK_INSET = 4;

const PX_PER_MM = 96 / 25.4;

export interface PageMetrics {
  /** Page size in CSS pixels at 100% zoom. */
  width: number;
  height: number;
  margin: number;
  columns: number;
  columnWidth: number;
  rowHeight: number;
  /** How many rows fit between the margins. */
  rows: number;
}

export function pageMetrics(setup: PageSetup): PageMetrics {
  const paper = PAPER_SIZES[setup.size];
  const long = Math.round(Math.max(paper.widthMm, paper.heightMm) * PX_PER_MM);
  const short = Math.round(Math.min(paper.widthMm, paper.heightMm) * PX_PER_MM);
  const [width, height] = setup.orientation === "portrait" ? [short, long] : [long, short];
  const columnWidth = (width - 2 * PAGE_MARGIN) / GRID_COLUMNS;
  const rowHeight = columnWidth / 2;
  return {
    width,
    height,
    margin: PAGE_MARGIN,
    columns: GRID_COLUMNS,
    columnWidth,
    rowHeight,
    rows: Math.floor((height - 2 * PAGE_MARGIN) / rowHeight),
  };
}

/** A block's box on the page, in pixels. */
export function blockBox(rect: BlockRect, metrics: PageMetrics) {
  return {
    left: metrics.margin + rect.x * metrics.columnWidth + BLOCK_INSET,
    top: metrics.margin + rect.y * metrics.rowHeight + BLOCK_INSET,
    width: rect.w * metrics.columnWidth - 2 * BLOCK_INSET,
    height: rect.h * metrics.rowHeight - 2 * BLOCK_INSET,
  };
}

// ---------------------------------------------------------------- Editing
// Moving and resizing work in whole cells and never leave the page's grid;
// whether a block may land where it is dropped is decided by `isFree`.

export type ResizeEdges = { left?: boolean; right?: boolean; top?: boolean; bottom?: boolean };

export const MIN_WIDGET_ROWS = 4;

/** The smallest a block can be: a widget needs room to draw, the rest one cell. */
export function minBlockSize(content: BlockContent): { w: number; h: number } {
  return content.kind === "widget" ? { w: 3, h: MIN_WIDGET_ROWS } : { w: 1, h: 1 };
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), Math.max(min, max));

/** The block moved by whole cells, kept inside the page's grid. */
export function moveRect(
  origin: BlockRect,
  dCols: number,
  dRows: number,
  metrics: PageMetrics,
): BlockRect {
  return {
    ...origin,
    x: clamp(origin.x + dCols, 0, metrics.columns - origin.w),
    y: clamp(origin.y + dRows, 0, metrics.rows - origin.h),
  };
}

/** The block with the given edges dragged by whole cells, kept inside the grid and above its minimum size. */
export function resizeRect(
  origin: BlockRect,
  edges: ResizeEdges,
  dCols: number,
  dRows: number,
  min: { w: number; h: number },
  metrics: PageMetrics,
): BlockRect {
  let { x, y, w, h } = origin;
  if (edges.left) {
    x = clamp(origin.x + dCols, 0, origin.x + origin.w - min.w);
    w = origin.x + origin.w - x;
  } else if (edges.right) {
    w = clamp(origin.w + dCols, min.w, metrics.columns - origin.x);
  }
  if (edges.top) {
    y = clamp(origin.y + dRows, 0, origin.y + origin.h - min.h);
    h = origin.y + origin.h - y;
  } else if (edges.bottom) {
    h = clamp(origin.h + dRows, min.h, metrics.rows - origin.y);
  }
  return { x, y, w, h };
}

export function overlaps(a: BlockRect, b: BlockRect): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

/** Whether the rect touches no block but `ignoreId`'s own. */
export function isFree(
  rect: BlockRect,
  blocks: ReportBlock[],
  ignoreId: string | null = null,
): boolean {
  return blocks.every((block) => block.id === ignoreId || !overlaps(rect, block.rect));
}

/** The first spot, reading left to right then top to bottom, where a block of this size fits. */
export function findFreeSpot(
  size: { w: number; h: number },
  blocks: ReportBlock[],
  metrics: PageMetrics,
): { x: number; y: number } | null {
  for (let y = 0; y + size.h <= metrics.rows; y++) {
    for (let x = 0; x + size.w <= metrics.columns; x++) {
      if (isFree({ x, y, w: size.w, h: size.h }, blocks)) return { x, y };
    }
  }
  return null;
}

// ------------------------------------------------------------- New paper
// A page's grid has 12 columns whatever the paper, but the number of rows
// follows its height (about 35 in portrait A4, 16 in landscape). So changing
// the paper scales the rows and keeps the columns, which keeps each block in
// the same place on the page, relative to its size.

/** Where a block lands on the new grid before collisions are sorted out: rows scaled, never smaller than its minimum. */
function scaledBlock(block: ReportBlock, ratio: number, metrics: PageMetrics): ReportBlock {
  const { x, y, w, h } = block.rect;
  const top = Math.round(y * ratio);
  const height = Math.min(
    metrics.rows,
    Math.max(minBlockSize(block.content).h, Math.round((y + h) * ratio) - top),
  );
  return { ...block, rect: { x, w, y: clamp(top, 0, metrics.rows - height), h: height } };
}

/** `block` where it is if that's free, else pushed down below what's in the way, else in any free spot; null when the page has no room. */
function settleBlock(
  block: ReportBlock,
  placed: ReportBlock[],
  metrics: PageMetrics,
): ReportBlock | null {
  let rect = block.rect;
  while (!isFree(rect, placed)) {
    const bottom = Math.max(
      ...placed
        .filter((other) => overlaps(rect, other.rect))
        .map((other) => other.rect.y + other.rect.h),
    );
    rect = { ...rect, y: bottom };
    if (rect.y + rect.h > metrics.rows) break;
  }
  if (rect.y + rect.h <= metrics.rows && isFree(rect, placed)) return { ...block, rect };
  const spot = findFreeSpot(rect, placed, metrics);
  return spot ? { ...block, rect: { ...rect, ...spot } } : null;
}

/**
 * The pages laid out again for another paper, so that nothing is lost or
 * left off the page: blocks keep their order and place, are pushed down off
 * any block that would now overlap them, and what still can't fit moves to
 * a new page right after its own.
 */
export function refitPages(pages: ReportPage[], from: PageSetup, to: PageSetup): ReportPage[] {
  const before = pageMetrics(from);
  const after = pageMetrics(to);
  if (before.rows === after.rows) return pages;
  const ratio = after.rows / before.rows;
  const result: ReportPage[] = [];
  for (const page of pages) {
    let current: ReportPage = { ...page, blocks: [] };
    result.push(current);
    let queue = [...page.blocks]
      .sort((a, b) => a.rect.y - b.rect.y || a.rect.x - b.rect.x)
      .map((block) => scaledBlock(block, ratio, after));
    while (queue.length > 0) {
      const overflow: ReportBlock[] = [];
      for (const block of queue) {
        const settled = settleBlock(block, current.blocks, after);
        if (settled) current.blocks.push(settled);
        else overflow.push(block);
      }
      if (overflow.length === 0) break;
      current = { id: crypto.randomUUID(), blocks: [] };
      result.push(current);
      queue = overflow;
    }
  }
  return result;
}
