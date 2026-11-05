import type { ViewState } from "../store/types";
import { querySql, type CustomQuery } from "./custom-query";

// The widgets on an inspection's page. Built-in inspections are fixed lists
// of widget ids; the user's inspections hold their own items.

export type CollectionViewType = "table" | "map" | "chart";
export type TableSort = "label-asc" | "value-desc" | "value-asc" | "difference-desc";

/** A table/map/chart of one result collection, with the state it was left in. */
export interface CollectionWidgetState {
  collectionId: string;
  viewType: CollectionViewType;
  tableSort: TableSort;
  pinnedChartLabel: string | null;
  mapViewState: ViewState;
}

export type CustomChart = "bar" | "stacked-bar" | "line" | "area" | "table" | "number" | "map";

/** A widget the user builds: a query of a result table and how to draw it. */
export interface CustomWidgetState {
  title: string;
  subtitle: string;
  /** Which editor the user last worked in. */
  mode: "builder" | "sql";
  /** The SQL as the user wrote it; the builder rewrites it on every change. */
  sql: string;
  /** What the widget shows: the builder's query, or the last SQL that ran. */
  query: CustomQuery;
  chart: CustomChart;
  mapViewState: ViewState;
}

export type WidgetSetItem =
  | { id: string; kind: "preset"; widgetId: string }
  | ({ id: string; kind: "custom" } & CustomWidgetState)
  // Markdown text the user writes onto the page.
  | { id: string; kind: "note"; text: string }
  // The earlier result table/map/chart widget, kept so saved inspections still open.
  | ({ id: string; kind: "collection" } & CollectionWidgetState);
export type CollectionItem = Extract<WidgetSetItem, { kind: "collection" }>;
export type CustomItem = Extract<WidgetSetItem, { kind: "custom" }>;
export type NoteItem = Extract<WidgetSetItem, { kind: "note" }>;

/** A copy of the item with its own id, for adding it somewhere else. */
export function copyWidgetItem(item: WidgetSetItem): WidgetSetItem {
  return { ...item, id: crypto.randomUUID() };
}

export function presetItem(widgetId: string): WidgetSetItem {
  return { id: crypto.randomUUID(), kind: "preset", widgetId };
}

export function builtInItems(widgetIds: string[]): WidgetSetItem[] {
  return widgetIds.map(presetItem);
}

export function newCustomItem(
  state: Pick<CustomWidgetState, "title" | "subtitle" | "query" | "chart" | "mapViewState">,
): CustomItem {
  return {
    id: crypto.randomUUID(),
    kind: "custom",
    mode: "builder",
    sql: querySql(state.query),
    ...state,
  };
}

export function newNoteItem(): NoteItem {
  return { id: crypto.randomUUID(), kind: "note", text: "" };
}
