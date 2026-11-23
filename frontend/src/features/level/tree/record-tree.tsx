// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Tree, type NodeRendererProps, type RowRendererProps, type TreeApi } from "react-arborist";
import { LuBoxes, LuCircleDot, LuFolder, LuFolderOpen, LuMapPin, LuTag } from "react-icons/lu";
import {
  buildTree,
  busNodeId,
  carrierNodeId,
  ctypeNodeId,
  loadChildren,
  locationNodeId,
  type TreeNode,
  type TreeNodeKind,
} from "./tree-nodes";
import { useElementSize } from "../../project/lib/use-element-size";
import { useProjectStore } from "../../project/store/project-store";
import { isDropped, readShown, useShownCatalog, useShownData } from "../../project/lib/record-data";
import { useOpenRecordPage, useOpenRecordPageId } from "../../project/lib/use-record-page";
import { levelOfPageId, levelPageId, type Level } from "../level";
import { usePeriods } from "../periods";
import { treeCounts, treeLocations } from "./tree-queries";
import { useLastReady } from "./use-last-ready";
import { RecordSearchBox, RecordSearchResults } from "./record-search";
import { ShownScenarioNote } from "../scenarios/shown-scenario-note";
import {
  RecordTreeSkeletonHeader,
  RecordTreeSkeletonRows,
  TreePlaceholderRow,
} from "./record-tree-skeleton";
import { TreeToggle } from "./tree-toggle";
import { activateTreeRow } from "./tree-actions";

// The record's tree beside its pages (Build and Inspect): Entities › type ›
// carrier › entity, and Locations › location › bus › entity, built by
// recordTree.ts, with the "Showing" line and search. Every row is a level:
// a click (or Enter) opens it and unfolds the row; the chevron folds. The
// open level's row stays marked. Counts and lists are of the entities
// active in the shown investment period.

const ICON: Record<Exclude<TreeNodeKind, "category" | "placeholder" | "more">, typeof LuBoxes> = {
  ctype: LuBoxes,
  carrier: LuTag,
  location: LuMapPin,
  bus: LuCircleDot,
  entity: LuCircleDot,
};

// react-arborist indents from 0; rows start 12px in, like the other sidebar lists.
const BASE_LEFT_PADDING = 12;
const INITIAL_OPEN_STATE = { entities: true, locations: false };

/** Opens a level on the current tab. */
function useOpenLevel() {
  const openRecordPage = useOpenRecordPage();
  return useCallback((level: Level) => openRecordPage(levelPageId(level)), [openRecordPage]);
}

function TreeRow({ node, style }: NodeRendererProps<TreeNode>) {
  const { kind, color, level, pill } = node.data;
  const openLevel = useOpenLevel();
  const openPageId = useOpenRecordPageId();
  const paddingLeft = (style.paddingLeft as number) + BASE_LEFT_PADDING;

  if (kind === "placeholder")
    return <TreePlaceholderRow node={node.data} style={style} paddingLeft={paddingLeft} />;

  const open = level ? () => openLevel(level) : null;
  // "n more in the table": opens the level whose table lists them all.
  if (kind === "more") {
    return (
      <div
        title={node.data.title}
        style={{ ...style, paddingLeft: paddingLeft + 20 }}
        onClick={() => open?.()}
        className="text-surface-500 hover:bg-surface-700/60 hover:text-surface-300 flex h-full cursor-pointer items-center pr-2 text-[11px]"
      >
        {node.data.name}
      </div>
    );
  }

  const isCategory = kind === "category";
  const Icon = isCategory ? (node.isOpen ? LuFolderOpen : LuFolder) : ICON[kind];
  // The row of the open level stays marked.
  const isOpenLevel = level !== undefined && levelPageId(level) === openPageId;
  return (
    <div
      title={node.data.title}
      style={{ ...style, paddingLeft }}
      onClick={() => activateTreeRow(node, open)}
      className={`group flex h-full cursor-pointer items-center gap-1 pr-2 text-[12px] ${isOpenLevel ? "bg-accent-600/25 text-surface-50" : node.isFocused ? "bg-surface-700/40 text-surface-100" : "text-surface-200 hover:bg-surface-700/60"}`}
    >
      <TreeToggle node={node} />
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
            ? "text-surface-300 ml-0.5 min-w-0 flex-1 truncate text-[11px] font-semibold tracking-wide uppercase"
            : "ml-0.5 min-w-0 flex-1 truncate"
        }
      >
        {node.data.name}
      </span>
      {pill && (
        <span
          title={`Region ${pill}`}
          className="border-surface-600 text-surface-400 max-w-20 shrink-0 truncate rounded-full border px-1.5 text-[10px] leading-4"
        >
          {pill}
        </span>
      )}
      {node.data.detail && (
        <span className="text-surface-500 ml-auto shrink-0 text-[10px] tabular-nums">
          {node.data.detail}
        </span>
      )}
    </div>
  );
}

// Rows shrink to the panel and truncate, instead of react-arborist's
// max-content width that scrolls the panel sideways.
function TruncatingRow({ node, attrs, innerRef, children }: RowRendererProps<TreeNode>) {
  return (
    <div
      {...attrs}
      ref={innerRef}
      style={{ ...attrs.style, minWidth: 0 }}
      onFocus={(event) => event.stopPropagation()}
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

/** The tree row a level is, and for a bus the location row it sits under. */
function rowOfLevel(level: Level | null): { id: string; location?: string } | null {
  switch (level?.kind) {
    case "component":
      return { id: ctypeNodeId(level.ctype) };
    case "carrier":
      return { id: carrierNodeId(level.ctype, level.carrier) };
    case "location":
      return { id: locationNodeId(level.location) };
    case "bus":
      return level.location === null
        ? null
        : { id: busNodeId(level.bus, level.location), location: locationNodeId(level.location) };
    default:
      return null;
  }
}

export function RecordTree() {
  const record = useProjectStore((s) => s.record);
  const recordStatus = useProjectStore((s) => s.recordStatus);
  const reconnect = useProjectStore((s) => s.reconnect);
  const { period } = usePeriods();
  const counts = useLastReady(
    useShownData("tree-counts", period === null ? null : [period], () => treeCounts(period!)),
  );
  const locations = useLastReady(
    useShownData("tree-locations", period === null ? null : [period], () => treeLocations(period!)),
  );
  const [containerRef, size] = useElementSize<HTMLDivElement>();
  const [loaded, setLoaded] = useState<Record<string, TreeNode[]>>({});
  const [search, setSearch] = useState("");
  const treeRef = useRef<TreeApi<TreeNode> | null>(null);
  const openLevel = useOpenLevel();
  const { catalog } = useShownCatalog();
  // Folders asked for: loaded, loading, or waiting out a scenario switch.
  const wanted = useRef(new Set<string>());
  const loading = useRef(new Set<string>());

  const treeData = useMemo(
    () => (record && counts && locations ? buildTree(record, counts, locations, loaded) : null),
    [counts, loaded, locations, record],
  );
  // A location's buses are found in the tree as built, loaded lists included.
  const treeDataRef = useRef(treeData);
  treeDataRef.current = treeData;

  // One folder's children in the shown catalog and period: from the cache
  // at once if read before, else read. Until then the folder shows what it
  // had, or skeleton rows. During a switch (no catalog) it waits; the
  // switch's end loads it.
  const fetchChildren = useCallback(
    (id: string, force: boolean) => {
      wanted.current.add(id);
      const key = `${catalog}\n${period}\n${id}`;
      if (
        !record ||
        !catalog ||
        period === null ||
        (!force && loaded[id]) ||
        loading.current.has(key)
      )
        return;
      const lazy = findNode(treeDataRef.current ?? [], id)?.lazy;
      if (!lazy) return;
      const { cached, read } = readShown("tree-children", catalog, [id, period], () =>
        loadChildren(lazy, id, record, period),
      );
      if (cached) {
        setLoaded((current) => ({ ...current, [id]: orNone(id, cached) }));
        return;
      }
      loading.current.add(key);
      read()
        .then((children) => setLoaded((current) => ({ ...current, [id]: orNone(id, children) })))
        .catch((error: unknown) => {
          if (isDropped(error)) return;
          console.error("Failed to load tree children", error);
          setLoaded((current) => ({
            ...current,
            [id]: [{ id: `${id}/error`, name: "Failed to load", kind: "placeholder" }],
          }));
        })
        .finally(() => loading.current.delete(key));
    },
    [catalog, loaded, period, record],
  );
  const ensureLoaded = useCallback((id: string) => fetchChildren(id, false), [fetchChildren]);

  // Another scenario or period shown: every folder asked for, read again.
  // The previous lists stay until each arrives.
  useEffect(() => {
    for (const id of wanted.current) fetchChildren(id, true);
    // Only when the catalog or period changes.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, period]);

  // The open level's row is unfolded to and scrolled into view, e.g. after
  // a link or a search pick. Once per level, so later loads don't reopen
  // folders closed since. A bus waits for its location's buses.
  const openPageId = useOpenRecordPageId();
  const revealed = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const api = treeRef.current;
    if (!api || !treeData || revealed.current === openPageId) return;
    const row = rowOfLevel(levelOfPageId(openPageId));
    if (
      row &&
      !findNode(treeData, row.id) &&
      row.location &&
      findNode(treeData, row.location) &&
      !loaded[row.location]
    ) {
      // Its buses arrive with a new treeData, which runs this again.
      ensureLoaded(row.location);
      return;
    }
    revealed.current = openPageId;
    if (!row || !findNode(treeData, row.id)) return;
    api.openParents(row.id);
    void api.scrollTo(row.id);
  }, [ensureLoaded, loaded, openPageId, size.height, treeData]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* The server opens a record on its first use, which can take a while. */}
      {!treeData && recordStatus !== "error" && <RecordTreeSkeletonHeader />}
      <ShownScenarioNote />
      {treeData && (
        <RecordSearchBox
          term={search}
          onChange={setSearch}
          placeholder="Find an entity, carrier or location"
        />
      )}
      <div
        ref={containerRef}
        className="relative min-h-0 flex-1 overflow-hidden py-1"
        // Enter opens the focused row, as a click does (the tree's arrow keys fold).
        onKeyDown={(event) => {
          const node = treeRef.current?.focusedNode;
          if (event.key !== "Enter" || !node || node.data.kind === "placeholder") return;
          event.preventDefault();
          const { level } = node.data;
          if (node.data.kind === "more") {
            if (level) openLevel(level);
            return;
          }
          activateTreeRow(node, level ? () => openLevel(level) : null);
        }}
      >
        {/* Over the tree rather than instead of it, so the tree keeps its
            open folders for when the search clears. */}
        {treeData && search.trim() && period !== null && (
          <div
            className="bg-surface-800 absolute inset-0 z-10"
            onKeyDown={(event) => event.stopPropagation()}
          >
            <RecordSearchResults term={search} period={period} />
          </div>
        )}
        {!treeData ? (
          recordStatus === "error" ? (
            <div className="text-surface-400 flex h-full items-center justify-center px-4 text-center text-[12px]">
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
            </div>
          ) : (
            <RecordTreeSkeletonRows />
          )
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
              renderRow={TruncatingRow}
              onToggle={ensureLoaded}
            >
              {TreeRow}
            </Tree>
          )
        )}
      </div>
    </div>
  );
}
