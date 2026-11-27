// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { WidgetSetItem } from "../lib/widget-sets";
import type { ReportTheme } from "./report-themes";

// A report is a paper document built from Inspect widgets: pages of blocks
// laid out on a grid. Widget blocks reference the Inspect widget instead of
// copying it, so edits there flow into the report.

export type PaperSize = "a4" | "letter";
export type PaperOrientation = "portrait" | "landscape";

export interface PageSetup {
  size: PaperSize;
  orientation: PaperOrientation;
}

/** Where a widget block gets its widget from. */
export type WidgetRef =
  // One of the built-in inspections' widgets, by its id in PRESET_WIDGETS.
  | { source: "built-in"; widgetId: string }
  // An item on one of the user's own inspections.
  | { source: "inspection"; inspectionId: string; itemId: string }
  // A copy of an inspection's widget that the report owns: later edits to the
  // inspection, or deleting the widget there, leave it as it was.
  | { source: "detached"; item: WidgetSetItem };

export type BlockContent =
  // Each widget block shows its own run result, so a report can span several.
  // `title` replaces the widget's own title when set.
  | { kind: "widget"; ref: WidgetRef; resultId: string; title?: string }
  | { kind: "heading"; text: string; level: 1 | 2 | 3 }
  | { kind: "text"; text: string }
  | { kind: "divider" }
  | { kind: "image"; src: string; alt: string }
  | { kind: "shape"; shape: "rectangle" | "ellipse" | "line" };

/** Position and size in grid cells of the page. */
export interface BlockRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ReportBlock {
  id: string;
  rect: BlockRect;
  content: BlockContent;
}

export interface ReportPage {
  id: string;
  blocks: ReportBlock[];
}

export interface Report {
  id: string;
  name: string;
  /** ISO date-time. */
  createdAt: string;
  page: PageSetup;
  theme: ReportTheme;
  pages: ReportPage[];
}

export const PAPER_SIZES: Record<PaperSize, { label: string; widthMm: number; heightMm: number }> =
  {
    a4: { label: "A4", widthMm: 210, heightMm: 297 },
    letter: { label: "Letter", widthMm: 215.9, heightMm: 279.4 },
  };

export function newReportPage(): ReportPage {
  return { id: crypto.randomUUID(), blocks: [] };
}

export function pageSetupLabel(page: PageSetup): string {
  return `${PAPER_SIZES[page.size].label} · ${page.orientation === "portrait" ? "Portrait" : "Landscape"}`;
}
