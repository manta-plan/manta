import { create } from "zustand";
import type { ExpandableBlock } from "./fullscreen/fullscreen-context";
import { levelPageId, type Level } from "./level";
import type { CrossFilter } from "./level-pick";

// What the parts of a level's page share: the investment period and time
// window (global, they survive navigation), the split's size, and what one
// part hands another — the table's filters (the map's location selection
// and the graph's groups set them), series picked in the table for the chart
// drawer, and the entity the table asks the map to focus.

/** A window of timesteps, ISO (UTC), `end` exclusive. */
export interface TimeWindow {
  start: string;
  end: string;
  /** What the window button says, e.g. "Winter" or "Mon 7 Jan – Sun 13 Jan". */
  label: string;
  /** A season: only these months (0 = January) count inside start..end, so Winter is not the months between its first and last day. */
  months?: readonly number[];
}

/** One column's filter in the table: a number range, a set of values, or a substring. */
export type ColumnFilter =
  | { kind: "range"; min: number | null; max: number | null }
  | { kind: "values"; values: string[] }
  | { kind: "contains"; text: string };

export interface ColumnSort {
  column: string;
  direction: "asc" | "desc";
}

/** A time series picked in the table: one entity's attribute (per bus for a value per bus). */
export interface PickedSeries {
  entity: string;
  ctype: string;
  attribute: string;
  bus: string | null;
  unit: string | null;
}

export type MapGraphTab = "map" | "graph";

export type MapFocus = { kind: "entity"; entity: string } | { kind: "route"; entity: string };

export type ChartDrawerMode = "statistics" | "attributes";

export const SPLIT_HEIGHT_DEFAULT = 430;
export const SPLIT_HEIGHT_MIN = 200;
export const SPLIT_HEIGHT_MAX = 900;
/** The table's share of the split's width by default, and the limits a drag keeps to. */
export const SPLIT_RATIO_DEFAULT = 0.58;
export const SPLIT_RATIO_MIN = 0.35;
export const SPLIT_RATIO_MAX = 0.8;

interface LevelState {
  /** The investment period shown (a snapshot period, as text); null until the record's periods are read. */
  period: string | null;
  setPeriod: (period: string) => void;
  /** The time window inside the period; null is its full span. */
  timeWindow: TimeWindow | null;
  setTimeWindow: (window: TimeWindow | null) => void;

  /** Map & graph's tab, and whether it's shown ("Map & graph" in the table header). */
  mapGraphTab: MapGraphTab;
  setMapGraphTab: (panel: MapGraphTab) => void;
  isMapGraphOpen: boolean;
  setMapGraphOpen: (open: boolean) => void;
  /** The block shown full screen, in a dialog over the page (the table, Map & graph or the chart drawer). */
  expandedBlock: ExpandableBlock | null;
  setExpandedBlock: (block: ExpandableBlock | null) => void;
  /** The split's height (px) and the table's share of its width. */
  splitHeight: number;
  setSplitHeight: (height: number) => void;
  splitRatio: number;
  setSplitRatio: (ratio: number) => void;

  /** Locations selected on the map: the table shows only entities there (a line if either end is). Kept across levels. */
  selectedLocations: string[];
  setSelectedLocations: (locations: string[]) => void;
  toggleSelectedLocation: (location: string) => void;

  /** A pick from the other tree that narrows the level whose page id is `context` (level-pick). Cleared on navigation. */
  crossFilter: { context: string | null; filter: CrossFilter } | null;
  setCrossFilter: (context: string | null, filter: CrossFilter | null) => void;

  /** The table's column filters, by column key, and its sort. Cleared on navigation. */
  columnFilters: Record<string, ColumnFilter>;
  setColumnFilter: (column: string, filter: ColumnFilter | null) => void;
  columnSort: ColumnSort | null;
  setColumnSort: (sort: ColumnSort | null) => void;

  /** What the table asked the map to frame (Geolocated pin or route). Cleared on navigation. */
  mapFocus: MapFocus | null;
  setMapFocus: (focus: MapFocus | null) => void;

  /** Series picked in the table for the chart drawer, in pick order. */
  pickedSeries: PickedSeries[];
  togglePickedSeries: (series: PickedSeries) => void;
  setPickedSeries: (series: PickedSeries[]) => void;
  /** The chart drawer's mode, the statistic chosen (by base name, kept across levels that have it) and the attribute chosen in Attributes mode ("Generator · p_max_pu"). */
  chartMode: ChartDrawerMode | null;
  setChartMode: (mode: ChartDrawerMode) => void;
  chartStatistic: string | null;
  setChartStatistic: (statistic: string | null) => void;
  chartAttribute: string | null;
  setChartAttribute: (attribute: string | null) => void;
  chartAggregation: string | null;
  setChartAggregation: (aggregation: string | null) => void;

  /** On opening another level: what belongs to the last one goes. */
  resetForLevel: () => void;
  /** On opening another project: the period, window and selection belong to the last one. */
  resetForProject: () => void;
}

const sameSeries = (a: PickedSeries, b: PickedSeries) =>
  a.entity === b.entity && a.attribute === b.attribute && a.bus === b.bus;

export const useLevelStore = create<LevelState>((set) => ({
  period: null,
  // A window is absolute: the other period has none of its timesteps.
  setPeriod: (period) => set({ period, timeWindow: null }),
  timeWindow: null,
  setTimeWindow: (timeWindow) => set({ timeWindow }),

  mapGraphTab: "map",
  setMapGraphTab: (mapGraphTab) => set({ mapGraphTab, isMapGraphOpen: true }),
  isMapGraphOpen: true,
  setMapGraphOpen: (isMapGraphOpen) => set({ isMapGraphOpen }),
  expandedBlock: null,
  setExpandedBlock: (expandedBlock) => set({ expandedBlock }),
  splitHeight: SPLIT_HEIGHT_DEFAULT,
  setSplitHeight: (height) =>
    set({
      splitHeight: Math.round(Math.min(SPLIT_HEIGHT_MAX, Math.max(SPLIT_HEIGHT_MIN, height))),
    }),
  splitRatio: SPLIT_RATIO_DEFAULT,
  setSplitRatio: (ratio) =>
    set({ splitRatio: Math.min(SPLIT_RATIO_MAX, Math.max(SPLIT_RATIO_MIN, ratio)) }),

  selectedLocations: [],
  setSelectedLocations: (selectedLocations) =>
    set({ selectedLocations: [...new Set(selectedLocations)].sort() }),
  toggleSelectedLocation: (location) =>
    set((state) => ({
      selectedLocations: state.selectedLocations.includes(location)
        ? state.selectedLocations.filter((item) => item !== location)
        : [...state.selectedLocations, location].sort(),
    })),

  crossFilter: null,
  setCrossFilter: (context, filter) => set({ crossFilter: filter && { context, filter } }),

  columnFilters: {},
  setColumnFilter: (column, filter) =>
    set((state) => {
      const { [column]: _dropped, ...rest } = state.columnFilters;
      return { columnFilters: filter ? { ...rest, [column]: filter } : rest };
    }),
  columnSort: null,
  setColumnSort: (columnSort) => set({ columnSort }),

  mapFocus: null,
  setMapFocus: (mapFocus) =>
    set(mapFocus ? { mapFocus, isMapGraphOpen: true, mapGraphTab: "map" } : { mapFocus }),

  pickedSeries: [],
  togglePickedSeries: (series) =>
    set((state) => {
      if (state.pickedSeries.some((item) => sameSeries(item, series)))
        return { pickedSeries: state.pickedSeries.filter((item) => !sameSeries(item, series)) };
      // A series of another attribute starts the picks afresh.
      const kept = state.pickedSeries.filter(
        (item) => item.attribute === series.attribute && item.ctype === series.ctype,
      );
      return {
        pickedSeries: [...kept, series],
        chartMode: "attributes",
        chartAttribute: `${series.ctype} · ${series.attribute}`,
      };
    }),
  setPickedSeries: (pickedSeries) => set({ pickedSeries }),
  chartMode: null,
  setChartMode: (chartMode) => set({ chartMode }),
  chartStatistic: null,
  setChartStatistic: (chartStatistic) => set({ chartStatistic }),
  chartAttribute: null,
  setChartAttribute: (chartAttribute) => set({ chartAttribute, pickedSeries: [] }),
  chartAggregation: null,
  setChartAggregation: (chartAggregation) => set({ chartAggregation, pickedSeries: [] }),

  resetForLevel: () =>
    set({
      crossFilter: null,
      columnFilters: {},
      columnSort: null,
      mapFocus: null,
      pickedSeries: [],
      expandedBlock: null,
    }),
  resetForProject: () =>
    set({
      period: null,
      timeWindow: null,
      selectedLocations: [],
      crossFilter: null,
      columnFilters: {},
      columnSort: null,
      mapFocus: null,
      pickedSeries: [],
      expandedBlock: null,
    }),
}));

/** The cross-tree filter on `level`'s page; none while another level's is still in the store. */
export function useCrossFilter(level: Level): CrossFilter | null {
  const crossFilter = useLevelStore((s) => s.crossFilter);
  return crossFilter && crossFilter.context === levelPageId(level) ? crossFilter.filter : null;
}
