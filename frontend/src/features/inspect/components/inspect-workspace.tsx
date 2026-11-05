import { useCallback, useMemo, useRef, useState, type ComponentType } from "react";
import { Tooltip } from "@base-ui/react/tooltip";
import { Select } from "@base-ui/react/select";
import { Menu } from "@base-ui/react/menu";
import { GiMagnifyingGlass } from "react-icons/gi";
import {
  LuArrowDownUp,
  LuArrowLeftRight,
  LuBookmarkPlus,
  LuChartNoAxesCombined,
  LuCheck,
  LuChevronDown,
  LuChevronRight,
  LuCopy,
  LuDownload,
  LuListFilter,
  LuMap,
  LuPlus,
  LuRotateCcw,
  LuSlidersHorizontal,
  LuStickyNote,
  LuTableProperties,
  LuUndo2,
  LuX,
} from "react-icons/lu";
import { useLocation, useParams } from "wouter";
import type { IconType } from "react-icons";
import type { Run } from "../../project/data/runs";
import { DUMMY_RESULT_RUNS, runLabel } from "../../project/data/inspect-results";
import {
  BUILT_IN_INSPECTIONS,
  builtInInspection,
  type InspectionContent,
} from "../../project/data/inspections";
import { projectInspectHref } from "../../project/lib/project-route";
import { blankCustomItem } from "../../project/lib/blank-inspection";
import { RESULT_COLLECTIONS, type ResultCollection } from "../../project/data/result-collections";
import { useProjectStore } from "../../project/store/project-store";
import { ResultMap } from "./result-map";
import { resultAreaValues } from "../lib/result-map-data";
import { ResultChart } from "./result-chart";
import { resultChartPoints, sharedChartBounds } from "../lib/result-chart-data";
import { AddToMenu } from "./add-to-menu";
import { WidgetIconButton } from "./widget-icon-button";
import { ReorderSlot, type DropPlacement } from "./widget-reorder";
import { FilterNote } from "./filter-note";
import { InspectFilterDrawer } from "./inspect-filter-drawer";
import { InspectionNameDialog } from "./inspection-name-dialog";
import {
  DATA_DRAWER_DEFAULT_HEIGHT,
  WidgetDataButton,
  WidgetDataDrawer,
} from "./widget-data-drawer";
import { PRESET_WIDGETS } from "../lib/inspect-widget-registry";
import { CustomWidget } from "./custom-widget";
import { NoteWidget } from "./note-widget";
import { BUILT_IN_WIDGET_SPECS } from "../../project/lib/built-in-widget-specs";
import {
  EMPTY_FILTERS,
  InspectFilterContext,
  activeDimensions,
  collectionFilteredBy,
  filterCollection,
  useInspectFilters,
} from "../../project/lib/inspect-filters";
import {
  builtInItems,
  copyWidgetItem,
  newCustomItem,
  newNoteItem,
  presetItem,
  type CollectionItem,
  type CollectionViewType,
  type CollectionWidgetState,
  type CustomWidgetState,
  type TableSort,
  type WidgetSetItem,
} from "../../project/lib/widget-sets";
import {
  InspectionActionsContext,
  WidgetDataDrawerContext,
  WidgetItemContext,
  useScrollIntoViewWhen,
  useWidgetDataDrawer,
  type InspectionActionsValue,
  type WidgetDataDrawerValue,
} from "../../project/lib/widget-set-context";
import type { WidgetData } from "../../project/lib/widget-data";
import {
  ComparisonContext,
  ResultContext,
  type ComparisonValue,
} from "../../project/lib/result-comparison";

const COLLECTION_ITEMS = Object.fromEntries(
  RESULT_COLLECTIONS.map((item) => [item.id, item.label]),
);

const selectItemClassName =
  "flex h-7 cursor-default items-center gap-2 rounded px-2 text-[12px] text-surface-200 outline-none data-[highlighted]:bg-surface-700 data-[selected]:text-surface-50";

function RunOutputSelect({
  value,
  onValueChange,
  runs,
  includeNone = false,
}: {
  value: string | null;
  onValueChange: (value: string) => void;
  runs: Run[];
  includeNone?: boolean;
}) {
  // Lets the closed trigger show labels instead of raw run ids (and "None" for null).
  const items = [
    ...(includeNone ? [{ value: null, label: "None" }] : []),
    ...runs.map((run) => ({ value: run.id, label: runLabel(run) })),
  ];
  return (
    <Select.Root
      value={value}
      onValueChange={(nextValue) => onValueChange(nextValue ?? "")}
      items={items}
    >
      <Select.Trigger className="border-surface-600 bg-surface-800 text-surface-100 focus-visible:border-accent-500 flex h-7 max-w-52 min-w-48 items-center gap-2 rounded border px-2 text-left text-[12px] outline-none">
        <Select.Value className="min-w-0 flex-1 truncate" placeholder="Select output" />
        <Select.Icon className="text-surface-400">
          <LuChevronDown size={13} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner sideOffset={6} align="end" className="z-50">
          <Select.Popup className="border-surface-600 bg-surface-800 min-w-52 overflow-hidden rounded border p-1 shadow-xl outline-none">
            <Select.List>
              {includeNone && (
                <Select.Item
                  value={null}
                  className="text-surface-200 data-[highlighted]:bg-surface-700 data-[selected]:text-surface-50 flex h-7 cursor-default items-center gap-2 rounded px-2 text-[12px] outline-none"
                >
                  <Select.ItemText className="min-w-0 flex-1 truncate">None</Select.ItemText>
                  <Select.ItemIndicator className="text-accent-400">
                    <LuCheck size={13} />
                  </Select.ItemIndicator>
                </Select.Item>
              )}
              {runs.map((run) => (
                <Select.Item
                  key={run.id}
                  value={run.id}
                  className="text-surface-200 data-[highlighted]:bg-surface-700 data-[selected]:text-surface-50 flex h-7 cursor-default items-center gap-2 rounded px-2 text-[12px] outline-none"
                >
                  <Select.ItemText className="min-w-0 flex-1 truncate">
                    {runLabel(run)}
                  </Select.ItemText>
                  <Select.ItemIndicator className="text-accent-400">
                    <LuCheck size={13} />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}

function comparisonDelta(value: number, runId: string, rowIndex: number, columnIndex: number) {
  let hash = 0;
  for (const character of runId) hash = (hash * 31 + character.charCodeAt(0)) % 997;
  const adjustment = ((hash + rowIndex * 7 + columnIndex * 11) % 9) - 4;
  return value * (adjustment / 100);
}

const TABLE_SORT_LABELS: Record<TableSort, string> = {
  "label-asc": "Sort: label A-Z",
  "value-desc": "Sort: value high-low",
  "value-asc": "Sort: value low-high",
  "difference-desc": "Sort: difference high-low",
};

// Sorting by difference needs a comparison, so the cycle skips it without one.
function nextTableSort(sort: TableSort, hasComparison: boolean): TableSort {
  if (sort === "label-asc") return "value-desc";
  if (sort === "value-desc") return "value-asc";
  if (sort === "value-asc" && hasComparison) return "difference-desc";
  return "label-asc";
}

type ResultTableRow = {
  cells: (string | number)[];
  delta: number | null;
  rowIndex: number;
  value: number | null;
};

function tableRows(
  collection: ResultCollection,
  run: Run,
  comparisonRun: Run | null,
  sort: TableSort,
): ResultTableRow[] {
  return collection.rows
    .map((cells, rowIndex) => {
      const value =
        cells
          .slice(1)
          .filter((cell): cell is number => typeof cell === "number")
          .at(-1) ?? null;
      const delta =
        value === null
          ? null
          : comparisonDelta(value, comparisonRun?.id ?? run.id, rowIndex, cells.length - 1);
      return { cells, delta, rowIndex, value };
    })
    .sort((a, b) => {
      if (sort === "label-asc") return String(a.cells[0]).localeCompare(String(b.cells[0]));
      if (sort === "difference-desc") return (b.delta ?? 0) - (a.delta ?? 0);
      const difference = (a.value ?? 0) - (b.value ?? 0);
      return sort === "value-desc" ? -difference : difference;
    });
}

function ResultTable({
  collection,
  run,
  comparisonRun,
  sort,
}: {
  collection: ResultCollection;
  run: Run;
  comparisonRun: Run | null;
  sort: TableSort;
}) {
  const rows = tableRows(collection, run, comparisonRun, sort);

  return (
    <section className="border-surface-700 bg-surface-900 min-w-0 flex-1 overflow-auto border">
      <table className="w-full border-collapse text-[12px]">
        <thead className="bg-surface-800 text-surface-400 sticky top-0 text-left">
          <tr>
            {collection.columns.map((column) => (
              <th
                key={column}
                className="border-surface-700 border-b px-3 py-1.5 font-medium whitespace-nowrap"
              >
                {column}
              </th>
            ))}
            {comparisonRun && (
              <th className="border-surface-700 border-b px-3 py-1.5 text-right font-medium whitespace-nowrap">
                Difference
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ cells, delta, rowIndex }) => {
            return (
              <tr key={`${run.id}-${rowIndex}`} className="text-surface-200 hover:bg-surface-800">
                {cells.map((cell, columnIndex) => (
                  <td
                    key={columnIndex}
                    className={`border-surface-800 border-b px-3 py-1.5 whitespace-nowrap ${columnIndex === 0 ? "text-surface-100 font-mono" : "text-surface-300 text-right"}`}
                  >
                    {cell}
                  </td>
                ))}
                {comparisonRun && (
                  <td
                    className={`border-surface-800 border-b px-3 py-1.5 text-right tabular-nums ${delta === null ? "text-surface-500" : delta > 0 ? "text-ok-500" : delta < 0 ? "text-danger-500" : "text-surface-400"}`}
                  >
                    {delta === null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}`}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

const VIEW_OPTIONS: { id: CollectionViewType; label: string; icon: typeof LuTableProperties }[] = [
  { id: "table", label: "Table", icon: LuTableProperties },
  { id: "map", label: "Map", icon: LuMap },
  { id: "chart", label: "Chart", icon: LuChartNoAxesCombined },
];

function TableControlButton({
  icon: Icon,
  label,
  active,
  disabled,
  onClick,
}: {
  icon: IconType;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            aria-label={label}
            className={`flex h-7 w-7 items-center justify-center rounded outline-none ${active ? "bg-accent-600 text-white" : "text-surface-300 hover:bg-surface-700 hover:text-surface-50"} disabled:pointer-events-none disabled:opacity-40`}
          />
        }
      >
        <Icon size={14} />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className="border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

type PageRow = { kind: "item"; item: WidgetSetItem } | { kind: "numbers"; items: WidgetSetItem[] };

const isNumberItem = (item: WidgetSetItem) => item.kind === "custom" && item.chart === "number";

/** The page's widgets in rows: each on its own, except numbers next to each other, which share one. */
function pageRows(items: WidgetSetItem[]): PageRow[] {
  const rows: PageRow[] = [];
  for (const item of items) {
    const last = rows.at(-1);
    if (!isNumberItem(item)) rows.push({ kind: "item", item });
    else if (last?.kind === "numbers") last.items.push(item);
    else rows.push({ kind: "numbers", items: [item] });
  }
  return rows;
}

// The earlier custom view: a table, map or chart of one result collection.
// No longer offered, but kept so saved inspections that hold one still open.
function CollectionWidget({
  item,
  onChange,
  onDuplicate,
  onRemove,
  inspectionName,
  selectedRun,
  comparisonRun,
}: {
  item: CollectionItem;
  onChange: (patch: Partial<CollectionWidgetState>) => void;
  onDuplicate: () => void;
  onRemove: () => void;
  inspectionName: string;
  selectedRun: Run;
  comparisonRun: Run | null;
}) {
  const record = useProjectStore((s) => s.record);
  const { filters, allBuses } = useInspectFilters();
  const { viewType, pinnedChartLabel, mapViewState } = item;
  // A difference sort falls back to labels once the comparison is cleared.
  const tableSort =
    item.tableSort === "difference-desc" && !comparisonRun ? "label-asc" : item.tableSort;
  const sourceCollection =
    RESULT_COLLECTIONS.find((collection) => collection.id === item.collectionId) ??
    RESULT_COLLECTIONS[0];
  // The page's shared filters reshape the collection before any view reads it.
  const collection = useMemo(
    () => filterCollection(sourceCollection, filters, allBuses),
    [sourceCollection, filters, allBuses],
  );
  const primaryAreaValues = useMemo(
    () => resultAreaValues(record, collection, selectedRun.id),
    [record, collection, selectedRun],
  );
  const comparisonAreaValues = useMemo(
    () => (comparisonRun ? resultAreaValues(record, collection, comparisonRun.id) : []),
    [record, collection, comparisonRun],
  );
  const primaryChartPoints = useMemo(
    () => resultChartPoints(collection, selectedRun.id),
    [collection, selectedRun],
  );
  const comparisonChartPoints = useMemo(
    () => (comparisonRun ? resultChartPoints(collection, comparisonRun.id) : []),
    [collection, comparisonRun],
  );
  // One y-axis range for both charts so equal bar heights mean equal values.
  const chartBounds = useMemo(
    () => sharedChartBounds(primaryChartPoints, comparisonChartPoints),
    [primaryChartPoints, comparisonChartPoints],
  );
  // Shared color scale so the same shade means the same value on both maps.
  const mapDomain = useMemo<[number, number]>(() => {
    const allValues = [...primaryAreaValues, ...comparisonAreaValues].map((area) => area.value);
    return allValues.length > 0 ? [Math.min(...allValues), Math.max(...allValues)] : [0, 1];
  }, [primaryAreaValues, comparisonAreaValues]);
  // Both maps of a comparison share this widget's viewport, so they move in lockstep.
  const setMapViewState = (mapViewState: CollectionWidgetState["mapViewState"]) =>
    onChange({ mapViewState });
  const setPinnedChartLabel = (pinnedChartLabel: string | null) => onChange({ pinnedChartLabel });
  const comparisonGroup = `inspect-result-comparison-${item.id}`;
  const viewLabel =
    VIEW_OPTIONS.find((option) => option.id === viewType)?.label.toLowerCase() ?? viewType;
  const isDataOpen = useWidgetDataDrawer()?.isOpen ?? false;
  const sectionRef = useRef<HTMLElement>(null);
  useScrollIntoViewWhen(sectionRef, isDataOpen);
  // The selected result's rows, with the difference when comparing.
  const data = useMemo<WidgetData>(
    () => ({
      columns: [
        ...collection.columns,
        ...(comparisonRun ? [`Difference vs ${runLabel(comparisonRun)}`] : []),
      ],
      rows: tableRows(collection, selectedRun, comparisonRun, "label-asc").map((row) => [
        ...row.cells,
        ...(comparisonRun ? [row.delta === null ? null : Math.round(row.delta * 10) / 10] : []),
      ]),
    }),
    [collection, selectedRun, comparisonRun],
  );

  const downloadTable = () => {
    const rows = tableRows(collection, selectedRun, comparisonRun, tableSort);
    const cells = [
      [...collection.columns, ...(comparisonRun ? ["Difference"] : [])],
      ...rows.map((row) => [
        ...row.cells,
        ...(comparisonRun ? [row.delta === null ? "" : row.delta.toFixed(1)] : []),
      ]),
    ];
    const csv = cells
      .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${inspectionName.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}-${collection.id}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section
      ref={sectionRef}
      className={`bg-surface-900 flex h-[26rem] w-full shrink-0 flex-col border ${isDataOpen ? "border-accent-500" : "border-surface-700"}`}
    >
      <div className="border-surface-700 bg-surface-800 flex shrink-0 items-center gap-1 border-b px-3 py-2">
        {/* Categories differ per collection, so a pin can't carry across. */}
        <Select.Root
          value={item.collectionId}
          onValueChange={(value) =>
            value && onChange({ collectionId: value, pinnedChartLabel: null })
          }
          items={COLLECTION_ITEMS}
        >
          <Select.Trigger className="border-surface-600 bg-surface-900 text-surface-100 focus-visible:border-accent-500 flex h-7 min-w-52 items-center gap-2 rounded border px-2 text-left text-[12px] font-medium outline-none">
            <GiMagnifyingGlass size={13} className="text-surface-400 shrink-0" />
            <Select.Value className="min-w-0 flex-1 truncate" />
            <Select.Icon className="text-surface-400">
              <LuChevronDown size={13} />
            </Select.Icon>
          </Select.Trigger>
          <Select.Portal>
            <Select.Positioner sideOffset={6} align="start" className="z-50">
              <Select.Popup className="border-surface-600 bg-surface-800 min-w-52 overflow-hidden rounded border p-1 shadow-xl outline-none">
                <Select.List>
                  {RESULT_COLLECTIONS.map((collectionOption) => (
                    <Select.Item
                      key={collectionOption.id}
                      value={collectionOption.id}
                      className={selectItemClassName}
                    >
                      <Select.ItemText className="min-w-0 flex-1 truncate">
                        {collectionOption.label}
                      </Select.ItemText>
                      <Select.ItemIndicator className="text-accent-400">
                        <LuCheck size={13} />
                      </Select.ItemIndicator>
                    </Select.Item>
                  ))}
                </Select.List>
              </Select.Popup>
            </Select.Positioner>
          </Select.Portal>
        </Select.Root>
        {comparisonRun && (
          <span className="text-surface-400 ml-3 flex items-center gap-1.5 text-[11px]">
            <LuArrowLeftRight size={13} />
            Comparison enabled
          </span>
        )}
        {viewType === "table" && (
          <div className="ml-auto flex items-center gap-0.5">
            <TableControlButton
              icon={LuArrowDownUp}
              label={TABLE_SORT_LABELS[tableSort]}
              active={tableSort !== "label-asc"}
              onClick={() =>
                onChange({ tableSort: nextTableSort(tableSort, comparisonRun !== null) })
              }
            />
            <TableControlButton
              icon={LuRotateCcw}
              label="Reset table sort"
              onClick={() => onChange({ tableSort: "label-asc" })}
            />
            <TableControlButton icon={LuDownload} label="Download CSV" onClick={downloadTable} />
          </div>
        )}
        {viewType === "table" && <div aria-hidden className="bg-surface-600 mx-2 h-4 w-px" />}
        <div
          role="tablist"
          aria-label="Widget view"
          className={`${viewType === "table" ? "" : "ml-auto"} border-surface-600 bg-surface-900 flex items-center rounded border p-0.5`}
        >
          {VIEW_OPTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={viewType === id}
              onClick={() => onChange({ viewType: id })}
              className={`flex h-6 items-center gap-1 rounded px-2 text-[11px] font-medium outline-none ${viewType === id ? "bg-surface-700 text-surface-50" : "text-surface-400 hover:text-surface-100"}`}
            >
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>
        <div aria-hidden className="bg-surface-600 mx-2 h-4 w-px" />
        <FilterNote filteredBy={collectionFilteredBy(sourceCollection)} />
        <WidgetDataButton title={`${collection.label}: ${runLabel(selectedRun)}`} data={data} />
        <AddToMenu widgetName={`${collection.label} ${viewLabel}`} />
        <WidgetIconButton icon={LuCopy} label="Duplicate widget" onClick={onDuplicate} />
        <WidgetIconButton icon={LuX} label="Remove widget" onClick={onRemove} />
      </div>

      <div
        className={`min-h-0 flex-1 gap-3 overflow-auto p-3 ${comparisonRun ? "grid min-w-[52rem] grid-cols-2" : "flex"}`}
      >
        {viewType === "table" ? (
          <>
            <ResultTable
              collection={collection}
              run={selectedRun}
              comparisonRun={comparisonRun}
              sort={tableSort}
            />
            {comparisonRun && (
              <ResultTable
                collection={collection}
                run={comparisonRun}
                comparisonRun={selectedRun}
                sort={tableSort}
              />
            )}
          </>
        ) : viewType === "map" ? (
          <>
            <ResultMap
              title={runLabel(selectedRun)}
              collection={collection}
              values={primaryAreaValues}
              domain={mapDomain}
              viewState={mapViewState}
              onViewStateChange={setMapViewState}
              highlightedNames={filters.buses}
            />
            {comparisonRun && (
              <ResultMap
                title={runLabel(comparisonRun)}
                collection={collection}
                values={comparisonAreaValues}
                domain={mapDomain}
                viewState={mapViewState}
                onViewStateChange={setMapViewState}
                highlightedNames={filters.buses}
              />
            )}
          </>
        ) : (
          <>
            <ResultChart
              title={runLabel(selectedRun)}
              collection={collection}
              points={primaryChartPoints}
              bounds={chartBounds}
              comparison={
                comparisonRun
                  ? { title: runLabel(comparisonRun), points: comparisonChartPoints }
                  : undefined
              }
              pinnedLabel={pinnedChartLabel}
              onPinnedLabelChange={setPinnedChartLabel}
              comparisonGroup={comparisonGroup}
            />
            {comparisonRun && (
              <ResultChart
                title={runLabel(comparisonRun)}
                collection={collection}
                points={comparisonChartPoints}
                bounds={chartBounds}
                comparison={{ title: runLabel(selectedRun), points: primaryChartPoints }}
                pinnedLabel={pinnedChartLabel}
                onPinnedLabelChange={setPinnedChartLabel}
                comparisonGroup={comparisonGroup}
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}

// A built-in widget while the page compares results: one copy per result.
// The selected result's copy draws the card; the compared one renders its
// body into the card's right panel and shares pickers and map viewports.
function ComparedPresetWidget({
  Widget,
  itemId,
  selectedRun,
  comparisonRun,
}: {
  Widget: ComponentType<{ resultName: string }>;
  itemId: string;
  selectedRun: Run;
  comparisonRun: Run;
}) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const [comparisonData, setComparisonData] = useState<WidgetData | null>(null);
  const [shared, setSharedState] = useState<Record<string, unknown>>({});
  const setShared = useCallback(
    (key: string, value: unknown) => setSharedState((current) => ({ ...current, [key]: value })),
    [],
  );
  const base = useMemo<Omit<ComparisonValue, "role">>(
    () => ({
      primaryName: runLabel(selectedRun),
      comparisonName: runLabel(comparisonRun),
      slot,
      setSlot,
      comparisonData,
      setComparisonData,
      shared,
      setShared,
      chartGroup: `compare-${itemId}`,
    }),
    [selectedRun, comparisonRun, slot, comparisonData, shared, setShared, itemId],
  );
  const primary = useMemo<ComparisonValue>(() => ({ ...base, role: "primary" }), [base]);
  const compared = useMemo<ComparisonValue>(() => ({ ...base, role: "comparison" }), [base]);
  return (
    <>
      <ComparisonContext.Provider value={primary}>
        <ResultContext.Provider value={selectedRun.id}>
          <Widget resultName={runLabel(selectedRun)} />
        </ResultContext.Provider>
      </ComparisonContext.Provider>
      <ComparisonContext.Provider value={compared}>
        <ResultContext.Provider value={comparisonRun.id}>
          <Widget resultName={runLabel(comparisonRun)} />
        </ResultContext.Provider>
      </ComparisonContext.Provider>
    </>
  );
}

const menuItemClassName =
  "flex cursor-default items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:bg-accent-600 data-[highlighted]:text-white data-[popup-open]:bg-surface-700";
const menuPopupClassName =
  "min-w-56 max-w-72 rounded-md border border-surface-600 bg-surface-800 py-1 text-[12px] text-surface-100 shadow-2xl shadow-black/50 outline-none";

// Picks a widget for the page: a custom widget, a number, a note, or any built-in widget,
// grouped by the built-in inspection it comes from.
function AddWidgetMenu({ onAdd }: { onAdd: (item: WidgetSetItem) => void }) {
  return (
    <Menu.Root>
      <Menu.Trigger className="border-surface-600 text-surface-400 hover:border-accent-500 hover:text-surface-100 focus-visible:border-accent-500 data-[popup-open]:border-accent-500 data-[popup-open]:text-surface-100 flex h-10 shrink-0 items-center justify-center gap-1.5 rounded border border-dashed text-[12px] font-medium outline-none">
        <LuPlus size={13} />
        Add widget
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner className="z-50 outline-none" side="top" sideOffset={6}>
          <Menu.Popup className={menuPopupClassName}>
            <Menu.Item onClick={() => onAdd(blankCustomItem())} className={menuItemClassName}>
              <LuSlidersHorizontal size={13} className="shrink-0" />
              <span className="min-w-0 flex-1 truncate">Custom widget</span>
              <span className="text-surface-400 shrink-0 text-[11px]">Builder or SQL</span>
            </Menu.Item>
            <Menu.Item onClick={() => onAdd(newNoteItem())} className={menuItemClassName}>
              <LuStickyNote size={13} className="shrink-0" />
              <span className="min-w-0 flex-1 truncate">Note</span>
              <span className="text-surface-400 shrink-0 text-[11px]">Markdown text</span>
            </Menu.Item>
            <Menu.Separator className="bg-surface-600 my-1 h-px" />
            {BUILT_IN_INSPECTIONS.map((set) => (
              <Menu.SubmenuRoot key={set.id}>
                <Menu.SubmenuTrigger className={menuItemClassName}>
                  <span className="min-w-0 flex-1 truncate">{set.name}</span>
                  <LuChevronRight size={13} className="shrink-0" />
                </Menu.SubmenuTrigger>
                <Menu.Portal>
                  <Menu.Positioner className="z-50 outline-none" alignOffset={-4} sideOffset={2}>
                    <Menu.Popup className={menuPopupClassName}>
                      {set.widgetIds.map((widgetId) => (
                        <Menu.Item
                          key={widgetId}
                          onClick={() => onAdd(presetItem(widgetId))}
                          className={menuItemClassName}
                        >
                          <span className="min-w-0 flex-1 truncate">
                            {PRESET_WIDGETS[widgetId].label}
                          </span>
                        </Menu.Item>
                      ))}
                    </Menu.Popup>
                  </Menu.Positioner>
                </Menu.Portal>
              </Menu.SubmenuRoot>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

type NameDialogState = { mode: "save-as" } | { mode: "new-with-item"; item: WidgetSetItem } | null;

type PageContent = Required<InspectionContent>;

const DEFAULT_CONTENT: Omit<PageContent, "items"> = {
  resultId: DUMMY_RESULT_RUNS[0].id,
  comparisonResultId: "",
  filters: EMPTY_FILTERS,
};

// One inspection's page. Keyed by inspection, so each one opens fresh: a
// built-in starts from its defaults every time, and the user's own pick up
// where they were left.
function InspectionPage({ inspectionId }: { inspectionId: string }) {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const builtIn = builtInInspection(inspectionId);
  const userInspection = useProjectStore((s) =>
    builtIn ? null : (s.inspections.find((inspection) => inspection.id === inspectionId) ?? null),
  );
  const createInspection = useProjectStore((s) => s.createInspection);
  const updateInspectionContent = useProjectStore((s) => s.updateInspectionContent);
  // A built-in inspection's page lives only for this visit; it's never saved.
  const [session, setSession] = useState<PageContent & { isChanged: boolean }>(() => ({
    ...DEFAULT_CONTENT,
    items: builtIn ? builtInItems(builtIn.widgetIds) : [],
    isChanged: false,
  }));
  const [nameDialog, setNameDialog] = useState<NameDialogState>(null);
  const [isFilterDrawerOpen, setFilterDrawerOpen] = useState(false);
  const [dataItemId, setDataItemId] = useState<string | null>(null);
  // A custom widget the user just added opens with its editor.
  const [freshItemId, setFreshItemId] = useState<string | null>(null);
  // The widget being dragged by its grip, and where it would land.
  const [drag, setDrag] = useState<{
    id: string;
    overId: string | null;
    placement: DropPlacement;
  } | null>(null);
  const [dataDrawerHeight, setDataDrawerHeight] = useState(DATA_DRAWER_DEFAULT_HEIGHT);
  const [dataDrawerBody, setDataDrawerBody] = useState<HTMLDivElement | null>(null);
  const record = useProjectStore((s) => s.record);
  const allBuses = useMemo(
    () =>
      (record?.locations ?? [])
        .map((location) => location.location)
        .sort((a, b) => a.localeCompare(b)),
    [record],
  );

  const content: PageContent = userInspection
    ? {
        items: userInspection.items,
        resultId: userInspection.resultId ?? DEFAULT_CONTENT.resultId,
        comparisonResultId: userInspection.comparisonResultId ?? DEFAULT_CONTENT.comparisonResultId,
        filters: userInspection.filters ?? DEFAULT_CONTENT.filters,
      }
    : session;
  const { items, filters } = content;
  const filterContext = useMemo(() => ({ filters, allBuses }), [filters, allBuses]);
  const activeFilterCount = activeDimensions(filters).length;
  const selectedRun =
    DUMMY_RESULT_RUNS.find((run) => run.id === content.resultId) ?? DUMMY_RESULT_RUNS[0];
  const comparisonRun =
    DUMMY_RESULT_RUNS.find(
      (run) => run.id === content.comparisonResultId && run.id !== selectedRun.id,
    ) ?? null;
  const isBuiltInChanged = builtIn !== null && session.isChanged;
  const name = builtIn?.name ?? userInspection?.name ?? "";
  const description = builtIn?.description ?? userInspection?.description ?? "";

  // The user's own inspections save as they change.
  const updateContent = (patch: Partial<PageContent>) => {
    if (userInspection) updateInspectionContent(userInspection.id, patch);
    else setSession((current) => ({ ...current, ...patch }));
  };
  const setItems = (update: (items: WidgetSetItem[]) => WidgetSetItem[]) => {
    if (userInspection)
      updateInspectionContent(userInspection.id, {
        items: update(
          useProjectStore
            .getState()
            .inspections.find((inspection) => inspection.id === userInspection.id)?.items ?? [],
        ),
      });
    else setSession((current) => ({ ...current, items: update(current.items), isChanged: true }));
  };
  const updateItem = (id: string, patch: Partial<CollectionWidgetState>) =>
    setItems((current) =>
      current.map((item) =>
        item.id === id && item.kind === "collection" ? { ...item, ...patch } : item,
      ),
    );
  const updateCustomItem = (id: string, patch: Partial<CustomWidgetState>) =>
    setItems((current) =>
      current.map((item) =>
        item.id === id && item.kind === "custom" ? { ...item, ...patch } : item,
      ),
    );
  const updateNoteText = (id: string, text: string) =>
    setItems((current) =>
      current.map((item) => (item.id === id && item.kind === "note" ? { ...item, text } : item)),
    );
  // The copy goes right after its source.
  const duplicateItem = (id: string) =>
    setItems((current) =>
      current.flatMap((item) => (item.id === id ? [item, copyWidgetItem(item)] : [item])),
    );
  const removeItem = (id: string) =>
    setItems((current) => current.filter((item) => item.id !== id));
  const addItem = (item: WidgetSetItem) => {
    if (item.kind === "custom" || item.kind === "note") setFreshItemId(item.id);
    setItems((current) => [...current, item]);
  };
  // A custom copy of a built-in widget, right after it and open for editing.
  const editCopy = (id: string, widgetId: string) => {
    const spec = BUILT_IN_WIDGET_SPECS[widgetId];
    if (!spec) return;
    const copy = newCustomItem({
      title: PRESET_WIDGETS[widgetId].label,
      subtitle: "",
      ...spec,
      mapViewState: useProjectStore.getState().viewState,
    });
    setFreshItemId(copy.id);
    setItems((current) => current.flatMap((item) => (item.id === id ? [item, copy] : [item])));
  };
  const resetBuiltIn = () =>
    builtIn &&
    setSession((current) => ({
      ...current,
      items: builtInItems(builtIn.widgetIds),
      isChanged: false,
    }));
  // A result can't be compared with itself.
  const setResult = (resultId: string) =>
    updateContent({
      resultId,
      ...(content.comparisonResultId === resultId ? { comparisonResultId: "" } : {}),
    });

  const moveItem = (id: string, targetId: string, placement: DropPlacement) =>
    setItems((current) => {
      const moving = current.find((item) => item.id === id);
      if (!moving || id === targetId) return current;
      const rest = current.filter((item) => item.id !== id);
      const index = rest.findIndex((item) => item.id === targetId);
      if (index < 0) return current;
      rest.splice(placement === "before" ? index : index + 1, 0, moving);
      return rest;
    });
  const stepItem = (id: string, direction: -1 | 1) =>
    setItems((current) => {
      const index = current.findIndex((item) => item.id === id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  const reorderOf = (id: string) => ({
    onDragStart: () => setDrag({ id, overId: null, placement: "before" as DropPlacement }),
    onDragEnd: () => setDrag(null),
    onStep: (direction: -1 | 1) => stepItem(id, direction),
  });
  const renderItem = (item: WidgetSetItem) => {
    const onRemove = () => removeItem(item.id);
    if (item.kind === "preset") {
      const Widget = PRESET_WIDGETS[item.widgetId]?.component;
      // A saved inspection may name a widget that no longer exists (pageRows skips it).
      if (!Widget) return null;
      const onEditCopy = BUILT_IN_WIDGET_SPECS[item.widgetId]
        ? () => editCopy(item.id, item.widgetId)
        : undefined;
      return (
        <WidgetItemContext.Provider
          value={{ item, onRemove, onEditCopy, reorder: reorderOf(item.id) }}
        >
          {comparisonRun ? (
            <ComparedPresetWidget
              key={comparisonRun.id}
              Widget={Widget}
              itemId={item.id}
              selectedRun={selectedRun}
              comparisonRun={comparisonRun}
            />
          ) : (
            <ResultContext.Provider value={selectedRun.id}>
              <Widget resultName={runLabel(selectedRun)} />
            </ResultContext.Provider>
          )}
        </WidgetItemContext.Provider>
      );
    }
    if (item.kind === "note") {
      return (
        <WidgetItemContext.Provider value={{ item, onRemove, reorder: reorderOf(item.id) }}>
          <NoteWidget
            item={item}
            onChange={(text) => updateNoteText(item.id, text)}
            onDuplicate={() => duplicateItem(item.id)}
            startsEditing={item.id === freshItemId}
          />
        </WidgetItemContext.Provider>
      );
    }
    if (item.kind === "custom") {
      return (
        <WidgetItemContext.Provider value={{ item, onRemove, reorder: reorderOf(item.id) }}>
          <CustomWidget
            item={item}
            onChange={(patch) => updateCustomItem(item.id, patch)}
            onDuplicate={() => duplicateItem(item.id)}
            selectedRun={selectedRun}
            comparisonRun={comparisonRun}
            startsEditing={item.id === freshItemId}
          />
        </WidgetItemContext.Provider>
      );
    }
    return (
      <WidgetItemContext.Provider value={{ item, onRemove, reorder: reorderOf(item.id) }}>
        <CollectionWidget
          item={item}
          onChange={(patch) => updateItem(item.id, patch)}
          onDuplicate={() => duplicateItem(item.id)}
          onRemove={onRemove}
          inspectionName={name}
          selectedRun={selectedRun}
          comparisonRun={comparisonRun}
        />
      </WidgetItemContext.Provider>
    );
  };

  const inspectionActions: InspectionActionsValue = {
    currentInspectionId: inspectionId,
    addToInspection: (targetId, item) => {
      const target = useProjectStore
        .getState()
        .inspections.find((inspection) => inspection.id === targetId);
      if (target)
        updateInspectionContent(targetId, { items: [...target.items, copyWidgetItem(item)] });
    },
    addToNewInspection: (item) => setNameDialog({ mode: "new-with-item", item }),
  };

  // Close the data drawer once its widget leaves the page.
  const isDataOpen = dataItemId !== null && items.some((item) => item.id === dataItemId);
  const dataDrawer: WidgetDataDrawerValue = {
    openItemId: isDataOpen ? dataItemId : null,
    target: dataDrawerBody,
    toggle: (itemId) => setDataItemId((current) => (current === itemId ? null : itemId)),
    close: () => setDataItemId(null),
  };

  const confirmName = (newName: string) => {
    if (nameDialog?.mode === "new-with-item") {
      createInspection({
        name: newName,
        description: "",
        items: [copyWidgetItem(nameDialog.item)],
      });
    } else if (nameDialog?.mode === "save-as") {
      const created = createInspection({
        name: newName,
        description,
        ...content,
        items: items.map(copyWidgetItem),
      });
      navigate(projectInspectHref(projectId, created.id));
    }
    setNameDialog(null);
  };

  return (
    <div
      data-tour="inspect-main-section"
      className="bg-surface-900 relative flex h-full min-w-0 flex-col overflow-hidden"
    >
      <header className="border-surface-700 flex min-h-14 shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b px-5 py-2">
        <div className="mr-auto min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-surface-50 truncate text-[14px] font-semibold">{name}</h1>
            {builtIn && (
              <span className="border-surface-600 text-surface-400 shrink-0 rounded border px-1.5 text-[10px] font-medium tracking-wide uppercase">
                Built-in
              </span>
            )}
          </div>
          {description && (
            <p className="text-surface-400 mt-0.5 truncate text-[11px]">{description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isBuiltInChanged && (
            <TableControlButton icon={LuUndo2} label={`Reset ${name}`} onClick={resetBuiltIn} />
          )}
          <button
            type="button"
            onClick={() => setNameDialog({ mode: "save-as" })}
            className={`focus-visible:border-accent-500 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none ${
              isBuiltInChanged
                ? "border-accent-500/60 bg-accent-600/15 text-accent-300"
                : "border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700"
            }`}
          >
            <LuBookmarkPlus size={13} />
            Save as new inspection
          </button>
        </div>
        <label className="text-surface-400 flex items-center gap-2 text-[11px]">
          Result
          <RunOutputSelect
            value={selectedRun.id}
            onValueChange={setResult}
            runs={DUMMY_RESULT_RUNS}
          />
        </label>
        <label className="text-surface-400 flex items-center gap-2 text-[11px]">
          Compare
          <RunOutputSelect
            value={comparisonRun?.id ?? null}
            onValueChange={(comparisonResultId) => updateContent({ comparisonResultId })}
            runs={DUMMY_RESULT_RUNS.filter((run) => run.id !== selectedRun.id)}
            includeNone
          />
        </label>
        <button
          type="button"
          aria-pressed={isFilterDrawerOpen}
          onClick={() => setFilterDrawerOpen((open) => !open)}
          className={`focus-visible:border-accent-500 -ml-2 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none ${
            isFilterDrawerOpen || activeFilterCount > 0
              ? "border-accent-500/60 bg-accent-600/15 text-accent-300"
              : "border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700"
          }`}
        >
          <LuListFilter size={13} />
          Filters
          {activeFilterCount > 0 && (
            <span className="bg-accent-600 rounded-full px-1.5 text-[10px] leading-4 text-white">
              {activeFilterCount}
            </span>
          )}
        </button>
      </header>

      <InspectFilterContext.Provider value={filterContext}>
        <InspectionActionsContext.Provider value={inspectionActions}>
          <WidgetDataDrawerContext.Provider value={dataDrawer}>
            {/* Room below the last widget, so the drawer never hides it. */}
            <main
              className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4"
              style={isDataOpen ? { paddingBottom: dataDrawerHeight + 16 } : undefined}
              // A drop in the gap between widgets lands where the indicator last showed.
              onDragOver={(event) => {
                if (drag?.overId) event.preventDefault();
              }}
              onDrop={(event) => {
                if (!drag?.overId) return;
                event.preventDefault();
                moveItem(drag.id, drag.overId, drag.placement);
                setDrag(null);
              }}
            >
              {pageRows(
                items.filter((item) => item.kind !== "preset" || PRESET_WIDGETS[item.widgetId]),
              ).map((row) => {
                const slot = (item: WidgetSetItem, axis: "x" | "y", className?: string) => (
                  <ReorderSlot
                    key={item.id}
                    itemId={item.id}
                    axis={axis}
                    draggingId={drag?.id ?? null}
                    dropPlacement={drag?.overId === item.id ? drag.placement : null}
                    onDragOverItem={(placement) =>
                      setDrag((current) =>
                        current && (current.overId !== item.id || current.placement !== placement)
                          ? { ...current, overId: item.id, placement }
                          : current,
                      )
                    }
                    onDropOnItem={(placement) => {
                      if (drag) moveItem(drag.id, item.id, placement);
                      setDrag(null);
                    }}
                    className={className}
                  >
                    {renderItem(item)}
                  </ReorderSlot>
                );
                if (row.kind === "item") return slot(row.item, "y");
                // Numbers next to each other share a row; one being edited takes the whole row.
                return (
                  <div
                    key={`numbers-${row.items[0].id}`}
                    className={`grid shrink-0 gap-3 ${comparisonRun ? "grid-cols-2" : "grid-cols-3"}`}
                  >
                    {row.items.map((item) => slot(item, "x", "has-[[data-editing]]:col-span-full"))}
                  </div>
                );
              })}
              {items.length === 0 && (
                <div className="border-surface-700 flex h-40 shrink-0 flex-col items-center justify-center gap-1 rounded border text-center">
                  <div className="text-surface-200 text-[12px] font-medium">No widgets yet</div>
                  <div className="text-surface-400 text-[11px]">
                    Add one below, or send widgets here from other inspections with their Add to…
                    menu.
                  </div>
                </div>
              )}
              <AddWidgetMenu onAdd={addItem} />
            </main>
          </WidgetDataDrawerContext.Provider>
        </InspectionActionsContext.Provider>
      </InspectFilterContext.Provider>
      <WidgetDataDrawer
        isOpen={isDataOpen}
        height={dataDrawerHeight}
        onHeightChange={setDataDrawerHeight}
        onBodyRef={setDataDrawerBody}
      />
      {/* Covers the whole page, header included. */}
      <InspectFilterDrawer
        isOpen={isFilterDrawerOpen}
        onClose={() => setFilterDrawerOpen(false)}
        filters={filters}
        onChange={(nextFilters) => updateContent({ filters: nextFilters })}
        allBuses={allBuses}
      />
      <InspectionNameDialog
        open={nameDialog !== null}
        onOpenChange={(open) => !open && setNameDialog(null)}
        title="New inspection"
        description={
          nameDialog?.mode === "new-with-item"
            ? "Creates an inspection holding this widget."
            : `Saves this page, its ${items.length} widget${items.length === 1 ? "" : "s"}, result, comparison and filters, as an inspection of your own.`
        }
        initialName={nameDialog?.mode === "save-as" ? `${name} (copy)` : ""}
        confirmLabel="Save inspection"
        onConfirm={confirmName}
      />
    </div>
  );
}

export function InspectWorkspace() {
  const selectedInspectionId = useProjectStore((s) => s.selectedInspectionId);
  return selectedInspectionId ? (
    <InspectionPage key={selectedInspectionId} inspectionId={selectedInspectionId} />
  ) : null;
}
