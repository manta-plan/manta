import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Tree, type NodeRendererProps, type RowRendererProps, type TreeApi } from "react-arborist";
import {
  LuChevronRight,
  LuChevronDown,
  LuFolder,
  LuFolderOpen,
  LuBoxes,
  LuTag,
  LuClock3,
  LuCircleDot,
  LuTable,
  LuMapPin,
  LuLoaderCircle,
} from "react-icons/lu";
import { useProjectStore } from "../store/project-store";
import { ShownScenarioNote } from "./record-scenarios-panel";
import { useElementSize } from "../lib/use-element-size";
import {
  buildTree,
  DIMENSIONS_ID,
  ENTITIES_ID,
  entitiesNodeId,
  entityNodeId,
  loadChildren,
  type TreeNode,
  type TreeNodeKind,
} from "../lib/record-tree";

const ICON: Record<Exclude<TreeNodeKind, "category" | "placeholder">, typeof LuBoxes> = {
  ctype: LuBoxes,
  carrier: LuTag,
  dimension: LuClock3,
  group: LuMapPin,
  entity: LuCircleDot,
  label: LuCircleDot,
};

// react-arborist's row style is just `{ paddingLeft: indent }` with no base
// offset at depth 0, so root rows sit flush against the edge — add the same
// 12px ScenariosPanel's rows start with (px-3) on top of the per-depth indent.
const BASE_LEFT_PADDING = 12;
const INITIAL_OPEN_STATE = { [ENTITIES_ID]: true, [DIMENSIONS_ID]: true };

function RecordTreeRow({ node, style, dragHandle }: NodeRendererProps<TreeNode>) {
  const openItemDrawer = useProjectStore((s) => s.openItemDrawer);
  const openEntityTable = useProjectStore((s) => s.openEntityTable);
  const { kind, item, table, color } = node.data;
  const isCategory = kind === "category";

  if (kind === "placeholder") {
    return (
      <div
        style={{ ...style, paddingLeft: (style.paddingLeft as number) + BASE_LEFT_PADDING + 15 }}
        className="text-surface-500 flex h-full items-center gap-1.5 text-[11px]"
      >
        {node.data.name === "Loading…" && <LuLoaderCircle size={11} className="animate-spin" />}
        {node.data.name}
      </div>
    );
  }

  const Icon = isCategory ? (node.isOpen ? LuFolderOpen : LuFolder) : ICON[kind];

  return (
    <div
      ref={dragHandle}
      data-tour={node.data.id === ENTITIES_ID ? "model-tree-item" : undefined}
      title={node.data.title}
      style={{ ...style, paddingLeft: (style.paddingLeft as number) + BASE_LEFT_PADDING }}
      onClick={() => {
        if (node.isInternal) node.toggle();
        else if (item) openItemDrawer(item);
      }}
      className={`group flex h-full cursor-default items-center gap-1.5 pr-2 text-[12px] ${
        node.isSelected
          ? "bg-accent-600/25 text-surface-50"
          : "text-surface-200 hover:bg-surface-700/60"
      }`}
    >
      {node.isInternal ? (
        node.isOpen ? (
          <LuChevronDown size={12} className="text-surface-400 shrink-0" />
        ) : (
          <LuChevronRight size={12} className="text-surface-400 shrink-0" />
        )
      ) : (
        <span className="w-3 shrink-0" />
      )}
      {color ? (
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full border border-black/20"
          style={{ backgroundColor: color }}
        />
      ) : (
        <Icon
          size={13}
          className={isCategory ? "text-surface-300 shrink-0" : "text-accent-400 shrink-0"}
        />
      )}
      <span
        className={
          isCategory
            ? "text-surface-300 min-w-0 flex-1 truncate text-[11px] font-semibold tracking-wide uppercase"
            : "min-w-0 flex-1 truncate"
        }
      >
        {node.data.name}
      </span>
      {(node.data.detail || table) && (
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          {table && (
            <button
              type="button"
              title="Open in Table View"
              onClick={(event) => {
                event.stopPropagation();
                openEntityTable(table.ctype, table.carrier);
              }}
              className="text-surface-400 hover:bg-surface-600 hover:text-surface-50 hidden shrink-0 rounded p-0.5 outline-none group-hover:flex"
            >
              <LuTable size={12} />
            </button>
          )}
          {node.data.detail && (
            <span className="text-surface-500 text-[10px] tabular-nums">{node.data.detail}</span>
          )}
        </span>
      )}
    </div>
  );
}

// react-arborist gives every row `min-width: max-content` so a long/deeply
// nested node's selection highlight isn't clipped at the viewport edge —
// but that's also what forces the whole panel to scroll horizontally
// instead of letting long names ellipsis. We'd rather truncate, so this
// swaps that back to a normal shrinkable width.
function ScrollSafeRow({ node, attrs, innerRef, children }: RowRendererProps<TreeNode>) {
  return (
    <div
      {...attrs}
      ref={innerRef}
      style={{ ...attrs.style, minWidth: 0 }}
      onFocus={(e) => e.stopPropagation()}
      onClick={node.handleClick}
    >
      {children}
    </div>
  );
}

function findNode(nodes: TreeNode[], id: string): TreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = node.children ? findNode(node.children, id) : null;
    if (found) return found;
  }
  return null;
}

function orNone(id: string, children: TreeNode[]): TreeNode[] {
  return children.length > 0
    ? children
    : [{ id: `${id}/empty`, name: "None", kind: "placeholder" }];
}

export function ModelTreePanel() {
  const treeRef = useRef<TreeApi<TreeNode> | null>(null);
  const record = useProjectStore((s) => s.record);
  const recordStatus = useProjectStore((s) => s.recordStatus);
  const recordError = useProjectStore((s) => s.recordError);
  const reconnect = useProjectStore((s) => s.reconnect);
  const resolution = useProjectStore((s) => s.resolution);
  const selectedItem = useProjectStore((s) => s.selectedItem);
  const selectItem = useProjectStore((s) => s.selectItem);
  const [containerRef, size] = useElementSize<HTMLDivElement>();
  const [loaded, setLoaded] = useState<Record<string, TreeNode[]>>({});
  const loading = useRef(new Set<string>());

  const treeData = useMemo(() => (record ? buildTree(record, loaded) : null), [loaded, record]);

  // Bus labels group by zone when zonal, so they rebuild on a resolution change.
  useEffect(() => {
    setLoaded(({ "dimension:bus": _bus, ...rest }) => rest);
  }, [resolution]);

  const ensureLoaded = useCallback(
    (id: string) => {
      if (!record || !treeData || loaded[id] || loading.current.has(id)) return;
      const lazy = findNode(treeData, id)?.lazy;
      if (!lazy) return;
      loading.current.add(id);
      loadChildren(lazy, record, resolution)
        .then((children) => setLoaded((current) => ({ ...current, [id]: orNone(id, children) })))
        .catch((error: unknown) => {
          console.error("Failed to load tree children", error);
          setLoaded((current) => ({
            ...current,
            [id]: [{ id: `${id}/error`, name: "Failed to load", kind: "placeholder" }],
          }));
        })
        .finally(() => loading.current.delete(id));
    },
    [loaded, record, resolution, treeData],
  );

  // Another scenario: refetches the lists already loaded, which show the
  // previous scenario's until then. Open folders stay open.
  const shownScenario = useRef(record?.scenario);
  useEffect(() => {
    if (!record || shownScenario.current === record.scenario) return;
    shownScenario.current = record.scenario;
    const tree = buildTree(record, {});
    for (const id of Object.keys(loaded)) {
      const lazy = findNode(tree, id)?.lazy;
      if (!lazy) continue;
      loadChildren(lazy, record, resolution)
        .then((children) => setLoaded((current) => ({ ...current, [id]: orNone(id, children) })))
        .catch((error: unknown) => console.error("Failed to reload tree children", error));
    }
    // Only on a switch: the lists loaded at that moment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record]);

  // Reflects a selection made elsewhere (a line or location on the map) into
  // the tree: loads the entity's list if needed, opens its parents and
  // scrolls to it, without opening the item drawer. Once per selection: the
  // tree's own selection moves on when a folder is clicked, and later loads
  // mustn't reopen the entity's folders.
  const toReveal = useRef<string | null>(null);
  useEffect(() => {
    toReveal.current = selectedItem?.kind === "entity" ? entityNodeId(selectedItem.entity) : null;
  }, [selectedItem]);
  useEffect(() => {
    if (selectedItem?.kind !== "entity") return;
    const id = entityNodeId(selectedItem.entity);
    if (toReveal.current !== id) return;
    // A ctype without carriers lists its entities directly under it.
    const parentId = entitiesNodeId(selectedItem.ctype, selectedItem.carrier ?? "");
    const listId = findNode(treeData ?? [], parentId)
      ? parentId
      : entitiesNodeId(selectedItem.ctype, null);
    ensureLoaded(listId);
    const api = treeRef.current;
    if (!api || !loaded[listId]) return;
    toReveal.current = null;
    if (api.selectedIds.has(id)) return;
    api.openParents(id);
    api.select(id);
    void api.scrollTo(id);
  }, [ensureLoaded, loaded, selectedItem, treeData]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ShownScenarioNote />
      <div ref={containerRef} className="min-h-0 flex-1 overflow-hidden py-1">
        {!treeData ? (
          <div
            className="text-surface-400 flex h-full items-center justify-center px-4 text-center text-[12px]"
            title={recordError ?? undefined}
          >
            {recordStatus === "error" ? (
              <span>
                Can't reach the record server.{" "}
                <button
                  type="button"
                  onClick={reconnect}
                  className="text-accent-400 cursor-pointer font-medium hover:underline"
                >
                  Retry
                </button>
              </span>
            ) : (
              // The server opens a record on its first use, which can take a few seconds.
              "Opening the record…"
            )}
          </div>
        ) : (
          size.height > 0 && (
            <Tree<TreeNode>
              ref={treeRef}
              data={treeData}
              openByDefault={false}
              initialOpenState={INITIAL_OPEN_STATE}
              width={size.width}
              height={size.height}
              rowHeight={24}
              indent={16}
              disableDrag
              disableDrop
              disableEdit
              renderRow={ScrollSafeRow}
              onToggle={ensureLoaded}
              onSelect={(nodes) => {
                const item = nodes[0]?.data.item;
                if (item) selectItem(item);
              }}
            >
              {RecordTreeRow}
            </Tree>
          )
        )}
      </div>
    </div>
  );
}
