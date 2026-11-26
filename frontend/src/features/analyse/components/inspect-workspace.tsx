import { PageSkeleton } from "../../../components/widget-states";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import {
  LuBookmarkPlus,
  LuChevronRight,
  LuListFilter,
  LuPlus,
  LuRotateCcw,
  LuSlidersHorizontal,
  LuStickyNote,
} from "react-icons/lu";
import { useLocation, useParams } from "wouter";
import type { InspectResult } from "../lib/result-source";
import {
  BUILT_IN_INSPECTIONS,
  builtInInspection,
  type InspectionContent,
} from "../data/inspections";
import { projectAnalyseHref } from "../../project/lib/project-route";
import { blankCustomItem } from "../lib/blank-inspection";
import { useProjectStore } from "../../project/store/project-store";
import { showToast } from "../../../utils/toasts";
import { BuiltInWidget } from "./built-in-widget";
import { ReorderSlot, type DropPlacement } from "./widget-reorder";
import { InspectFilterDrawer } from "./inspect-filter-drawer";
import { InspectionNameDialog } from "./inspection-name-dialog";
import { DATA_DRAWER_DEFAULT_HEIGHT, WidgetDataDrawer } from "./widget-data-drawer";
import { PRESET_WIDGETS } from "./inspect-widget-registry";
import { CustomWidget } from "./custom-widget";
import { NoteWidget } from "./note-widget";
import { BUILT_IN_WIDGET_SPECS } from "../lib/built-in-widget-specs";
import {
  EMPTY_FILTERS,
  InspectFilterContext,
  activeDimensions,
  normalizeFilters,
} from "../lib/inspect-filters";
import {
  builtInItems,
  copyWidgetItem,
  newCustomItem,
  newNoteItem,
  presetItem,
  type CustomWidgetState,
  type WidgetSetItem,
} from "../lib/widget-sets";
import {
  InspectionActionsContext,
  WidgetDataDrawerContext,
  WidgetItemContext,
  type InspectionActionsValue,
  type WidgetDataDrawerValue,
} from "../lib/widget-set-context";
import { ResultContext } from "../lib/result-comparison";
import {
  ResultCatalogueContext,
  useLoadResultCatalogue,
  useResultCatalogue,
} from "../lib/use-result-data";
import {
  resolveResultSelection,
  useResultSelection,
  writeResultSelectionToUrl,
} from "../lib/inspect-result-selection";

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

const menuItemClassName =
  "flex cursor-pointer items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:bg-accent-600 data-[highlighted]:text-white data-[popup-open]:bg-surface-700 data-[popup-open]:text-surface-50";
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

// A custom widget or note just added opens with its editor. On a built-in
// view the add makes the user's copy and opens that page, so the page hands
// the widget's id over to the next one.
let handedOverFreshItem: string | null = null;

function takeHandedOverFreshItem() {
  const id = handedOverFreshItem;
  handedOverFreshItem = null;
  return id;
}

type NameDialogState = { mode: "save-as" } | { mode: "new-with-item"; item: WidgetSetItem } | null;

// The result and comparison are the tab's (see inspectResultSelection), not the page's.
type PageContent = Required<InspectionContent>;

const DEFAULT_CONTENT: Omit<PageContent, "items"> = { filters: EMPTY_FILTERS };

// The record shows the picked result itself: the tree, the item panel (with
// its Results section) and the view read it. Its catalog holds its
// scenario's inputs too. The record shows one revision for the whole
// project, so the Build and Inspect tabs follow (Build its scenario). A
// result's first open takes a while on the server; the tree's "Showing" line
// says it's loading meanwhile.
function useShowResult(result: InspectResult | null) {
  const showScenario = useProjectStore((s) => s.showScenario);
  const id = result?.id ?? null;
  useEffect(() => {
    if (id) showScenario(id);
  }, [id, showScenario]);
}

// One inspection's page. Keyed by inspection, so each one opens fresh: a
// built-in starts from its defaults every time, and the user's own pick up
// where they were left.
// It reads the toolbar's result and comparison, and the record follows.
function InspectionPage({ inspectionId }: { inspectionId: string }) {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const builtIn = builtInInspection(inspectionId);
  const userInspection = useProjectStore((s) =>
    builtIn ? null : (s.inspections.find((inspection) => inspection.id === inspectionId) ?? null),
  );
  const createInspection = useProjectStore((s) => s.createInspection);
  const updateInspectionContent = useProjectStore((s) => s.updateInspectionContent);
  const deleteInspection = useProjectStore((s) => s.deleteInspection);
  const openEditInspectionDrawer = useProjectStore((s) => s.openEditInspectionDrawer);
  // A built-in view's page lives only for this visit: how its widgets are
  // shown (table or map, a sort) isn't kept, and changing its widgets makes
  // it the user's own copy instead (forkBuiltIn).
  const [session, setSession] = useState<PageContent>(() => ({
    ...DEFAULT_CONTENT,
    items: builtIn ? builtInItems(builtIn.widgetIds) : [],
  }));
  const [nameDialog, setNameDialog] = useState<NameDialogState>(null);
  const [isFilterDrawerOpen, setFilterDrawerOpen] = useState(false);
  const [dataItemId, setDataItemId] = useState<string | null>(null);
  // A custom widget the user just added opens with its editor.
  // Also one handed over by a built-in view's page when the widget made its copy.
  const [freshItemId, setFreshItemId] = useState<string | null>(takeHandedOverFreshItem);
  // The widget being dragged by its grip, and where it would land.
  const [drag, setDrag] = useState<{
    id: string;
    overId: string | null;
    placement: DropPlacement;
  } | null>(null);
  const [dataDrawerHeight, setDataDrawerHeight] = useState(DATA_DRAWER_DEFAULT_HEIGHT);
  const [dataDrawerBody, setDataDrawerBody] = useState<HTMLDivElement | null>(null);
  const record = useProjectStore((s) => s.record);
  const catalogue = useResultCatalogue();
  const resultSelection = useResultSelection();
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
        filters: normalizeFilters(userInspection.filters),
      }
    : session;
  const { items, filters } = content;
  const filterContext = useMemo(() => ({ filters, allBuses }), [filters, allBuses]);
  const activeFilterCount = activeDimensions(filters).length;
  // The page only opens once the catalogue lists at least one result.
  const { selectedRun, comparisonRun } = resolveResultSelection(catalogue, resultSelection);
  useShowResult(selectedRun);
  const name = builtIn?.name ?? userInspection?.name ?? "";
  const description = builtIn?.description ?? userInspection?.description ?? "";

  // The user's own inspections save as they change.
  const updateContent = (patch: Partial<PageContent>) => {
    if (userInspection) updateInspectionContent(userInspection.id, patch);
    else setSession((current) => ({ ...current, ...patch }));
  };
  // Built-in views stay as they are: the first change to one's widgets saves
  // it, changed, as the user's own view and opens that, with a way back.
  const forkBuiltIn = (nextItems: WidgetSetItem[]) => {
    if (!builtIn) return;
    const taken = new Set(
      useProjectStore.getState().inspections.map((inspection) => inspection.name),
    );
    let copyName = `${builtIn.name} (copy)`;
    for (let n = 2; taken.has(copyName); n++) copyName = `${builtIn.name} (copy ${n})`;
    const created = createInspection({
      name: copyName,
      description: builtIn.description,
      filters: session.filters,
      items: nextItems,
    });
    navigate(projectAnalyseHref(projectId, created.id));
    showToast({
      title: `Saved as your view “${copyName}”`,
      description: `${builtIn.name} is built in, so your change went into a copy of it.`,
      action: {
        label: "Undo",
        onClick: () => {
          handedOverFreshItem = null;
          deleteInspection(created.id);
          navigate(projectAnalyseHref(projectId, builtIn.id));
        },
      },
      extraActions: [{ label: "Rename", onClick: () => openEditInspectionDrawer(created.id) }],
    });
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
    else forkBuiltIn(update(session.items));
  };
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
  const markFresh = (id: string) => {
    if (builtIn) handedOverFreshItem = id;
    setFreshItemId(id);
  };
  // On the user's own view, a removed widget can come back (a built-in view's removal already offers Undo on its copy).
  const removeItem = (id: string) => {
    const current = userInspection
      ? (useProjectStore
          .getState()
          .inspections.find((inspection) => inspection.id === userInspection.id)?.items ?? [])
      : items;
    const index = current.findIndex((item) => item.id === id);
    const removed = current[index];
    setItems((list) => list.filter((item) => item.id !== id));
    if (!userInspection || !removed) return;
    showToast({
      title: "Widget removed",
      action: {
        label: "Undo",
        onClick: () =>
          setItems((list) =>
            list.some((item) => item.id === id)
              ? list
              : [...list.slice(0, index), removed, ...list.slice(index)],
          ),
      },
    });
  };
  const addItem = (item: WidgetSetItem) => {
    if (item.kind === "custom" || item.kind === "note") markFresh(item.id);
    setItems((current) => [...current, item]);
  };
  // A built-in widget becomes its custom copy, in its place and open for editing.
  // (On a built-in view this change forks the view, which keeps the original.)
  const editCopy = (id: string, widgetId: string) => {
    const spec = BUILT_IN_WIDGET_SPECS[widgetId];
    if (!spec) return;
    const copy = newCustomItem({
      title: spec.label,
      subtitle: spec.subtitle,
      query: spec.query,
      chart: spec.chart,
      mapViewState: useProjectStore.getState().viewState,
    });
    markFresh(copy.id);
    setItems((current) => current.map((item) => (item.id === id ? copy : item)));
  };
  // A result can't be compared with itself.

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
          {/* One widget draws both results, so their charts share an order and a scale. */}
          <ResultContext.Provider value={selectedRun.id}>
            <BuiltInWidget
              widgetId={item.widgetId}
              resultName={selectedRun.label}
              comparison={comparisonRun}
            />
          </ResultContext.Provider>
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
          {/* So "Add to" sends the widget to a report with the result this page shows. */}
          <ResultContext.Provider value={selectedRun.id}>
            <CustomWidget
              item={item}
              onChange={(patch) => updateCustomItem(item.id, patch)}
              onDuplicate={() => duplicateItem(item.id)}
              selectedRun={selectedRun}
              comparisonRun={comparisonRun}
              startsEditing={item.id === freshItemId}
            />
          </ResultContext.Provider>
        </WidgetItemContext.Provider>
      );
    }
    return null;
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
      navigate(projectAnalyseHref(projectId, created.id));
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
          <button
            type="button"
            onClick={() => setNameDialog({ mode: "save-as" })}
            className="border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700 focus-visible:border-accent-500 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none"
          >
            <LuBookmarkPlus size={13} />
            Save as new view
          </button>
        </div>
        <button
          type="button"
          data-tour="view-filters"
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
              ).map((row, rowIndex) => {
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
                    // Not the first widget's id: removing or moving it would remount the row and reset the others.
                    key={`numbers-${rowIndex}`}
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
                    Add one below, or send widgets here from other views with their Add to… menu.
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
        periods={catalogue.periods}
      />
      <InspectionNameDialog
        open={nameDialog !== null}
        onOpenChange={(open) => !open && setNameDialog(null)}
        title="New view"
        description={
          nameDialog?.mode === "new-with-item"
            ? "Creates a view holding this widget."
            : `Saves this page, its ${items.length} widget${items.length === 1 ? "" : "s"} and filters, as a view of your own.`
        }
        initialName={nameDialog?.mode === "save-as" ? `${name} (copy)` : ""}
        confirmLabel="Save view"
        onConfirm={confirmName}
      />
    </div>
  );
}

function PageMessage({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="bg-surface-900 flex h-full flex-col items-center justify-center gap-1 px-6 text-center">
      <div className="text-surface-100 text-[13px] font-medium">{title}</div>
      <div className="text-surface-400 max-w-md text-[12px]">{detail}</div>
      {action}
    </div>
  );
}

// The page needs the result catalogue (which results and tables there are)
// before anything on it can draw.
// `pageId` is a view, on Analyze with the result and compare toolbar. (A
// type's or entity's page is RecordPages', on Build and Inspect.)
export function InspectWorkspace({ pageId: selectedInspectionId }: { pageId: string | null }) {
  const catalogueState = useLoadResultCatalogue();
  // `?result=&compare=` stay in the address bar while an
  // inspection is open, including after moving to another one (which
  // navigates to a bare path).
  const [location] = useLocation();
  const resultSelection = useResultSelection();
  useEffect(() => {
    writeResultSelectionToUrl();
    return () => writeResultSelectionToUrl(true);
  }, [location, resultSelection]);
  if (!selectedInspectionId) return null;
  if (catalogueState.status === "loading") return <PageSkeleton label="Loading the view" />;
  if (catalogueState.status === "error") {
    return (
      <PageMessage
        title="Couldn't load the results"
        detail={catalogueState.error}
        action={
          <button
            type="button"
            onClick={catalogueState.retry}
            className="border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700 focus-visible:border-accent-500 mt-2 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none"
          >
            <LuRotateCcw size={12} />
            Try again
          </button>
        }
      />
    );
  }
  if (catalogueState.catalogue.results.length === 0)
    return (
      <PageMessage
        title="No results in this record"
        detail="This project's record holds no solved results yet, so there's nothing to inspect."
      />
    );
  return (
    <ResultCatalogueContext.Provider value={catalogueState.catalogue}>
      <InspectionPage key={selectedInspectionId} inspectionId={selectedInspectionId} />
    </ResultCatalogueContext.Provider>
  );
}
