// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { BUILT_IN_WIDGET_SPECS } from "./built-in-widget-specs";
import { BUILT_IN_INSPECTIONS, type InspectionCanvas } from "../data/inspections";
import type { Report } from "../data/reports";
import { BUILT_IN_QUERIES, type BuiltInQuery } from "./result-queries";

// The Data panel's pages on Analyse: a computed table (`computed:supply`) or
// one of the result's raw tables (`raw:p_nom_opt`, an attribute view).

const COMPUTED = "computed:";
const RAW = "raw:";

export type DataPage =
  | { kind: "computed"; query: BuiltInQuery }
  | { kind: "raw"; attribute: string };

export function isDataPageId(pageId: string | null | undefined): pageId is string {
  return !!pageId && (pageId.startsWith(COMPUTED) || pageId.startsWith(RAW));
}

export const computedPageId = (name: string) => `${COMPUTED}${name}`;
export const rawPageId = (attribute: string) => `${RAW}${encodeURIComponent(attribute)}`;

/** The page an id names; null for an unknown computed table. */
export function dataPageOf(pageId: string | null | undefined): DataPage | null {
  if (!pageId) return null;
  if (pageId.startsWith(RAW))
    return { kind: "raw", attribute: decodeURIComponent(pageId.slice(RAW.length)) };
  if (!pageId.startsWith(COMPUTED)) return null;
  const query = BUILT_IN_QUERIES.find((item) => item.name === pageId.slice(COMPUTED.length));
  return query ? { kind: "computed", query } : null;
}

/** The computed tables that read a raw table (attributes.<name>). */
export function computedReading(attribute: string): BuiltInQuery[] {
  const pattern = new RegExp(
    `\\battributes\\.${attribute.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`,
  );
  return BUILT_IN_QUERIES.filter((query) => pattern.test(query.sql));
}

export interface TableUse {
  kind: "view" | "report";
  id: string;
  name: string;
  widgets: number;
}

/** The views and reports whose widgets read a computed table: built-in views, the project's own, and detached copies in reports. */
export function computedUses(
  name: string,
  views: InspectionCanvas[],
  reports: Report[],
): TableUse[] {
  const builtIn = BUILT_IN_INSPECTIONS.map((view) => ({
    kind: "view" as const,
    id: view.id,
    name: view.name,
    widgets: view.widgetIds.filter((id) => BUILT_IN_WIDGET_SPECS[id]?.query.table === name).length,
  }));
  const own = views.map((view) => ({
    kind: "view" as const,
    id: view.id,
    name: view.name,
    widgets: view.items.filter(
      (item) =>
        (item.kind === "custom" && item.query.table === name) ||
        (item.kind === "preset" && BUILT_IN_WIDGET_SPECS[item.widgetId]?.query.table === name),
    ).length,
  }));
  const inReports = reports.map((report) => ({
    kind: "report" as const,
    id: report.id,
    name: report.name,
    widgets: report.pages
      .flatMap((page) => page.blocks)
      .filter(
        (block) =>
          block.content.kind === "widget" &&
          block.content.ref.source === "detached" &&
          block.content.ref.item.kind === "custom" &&
          block.content.ref.item.query.table === name,
      ).length,
  }));
  return [...builtIn, ...own, ...inReports].filter((use) => use.widgets > 0);
}
