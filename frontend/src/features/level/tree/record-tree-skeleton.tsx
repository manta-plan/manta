import type { CSSProperties } from "react";
import type { TreeNode } from "./tree-nodes";
import { SidebarSkeletonBlock } from "../../../components/widget-states";
import { skeletonWidth } from "../../project/lib/skeleton";

// The record trees' loading states (the Build and Inspect tabs' alike):
// skeleton rows where a folder's children are loading, and the panel's shape
// while the record opens.

/** A placeholder child: a skeleton row while loading, else its note ("None", "Failed to load"). */
export function TreePlaceholderRow({
  node,
  style,
  paddingLeft,
}: {
  node: TreeNode;
  style: CSSProperties;
  paddingLeft: number;
}) {
  if (node.skeleton !== undefined) {
    return (
      <div
        style={{ ...style, paddingLeft }}
        role="status"
        aria-label="Loading"
        className="flex h-full items-center gap-1.5 pr-3"
      >
        <SidebarSkeletonBlock className="h-3 w-3 shrink-0 rounded-full" />
        <SidebarSkeletonBlock className="h-2.5" style={{ width: skeletonWidth(node.skeleton) }} />
      </div>
    );
  }
  return (
    <div
      style={{ ...style, paddingLeft: paddingLeft + 15 }}
      className="text-surface-500 flex h-full items-center text-[11px]"
    >
      {node.name}
    </div>
  );
}

// A folder row of the skeleton: chevron, icon, a bar for its name.
function FolderRow({ indent, width }: { indent: number; width: string }) {
  return (
    <div style={{ paddingLeft: indent }} className="flex h-6 items-center gap-1.5 pr-3">
      <SidebarSkeletonBlock className="h-2.5 w-2.5 shrink-0" />
      <SidebarSkeletonBlock className="h-3 w-3 shrink-0" />
      <SidebarSkeletonBlock className="h-2.5" style={{ width }} />
    </div>
  );
}

// While the record opens. Two parts, so the panel's measured tree area stays
// mounted (useElementSize observes it from the first render).

/** In place of the "Showing" line and the search box. */
export function RecordTreeSkeletonHeader() {
  return (
    <>
      <div className="border-surface-700 flex h-[23px] shrink-0 items-center border-b px-3">
        <SidebarSkeletonBlock className="h-2.5 w-40" />
      </div>
      <div className="border-surface-700 shrink-0 border-b px-2 py-1.5">
        <SidebarSkeletonBlock className="h-7 w-full" />
      </div>
    </>
  );
}

/** In the tree's area: the two folders and their first rows. */
export function RecordTreeSkeletonRows() {
  return (
    <div role="status" aria-label="Opening the record">
      <FolderRow indent={12} width="34%" />
      {[0, 1, 2, 3, 4].map((index) => (
        <FolderRow key={index} indent={28} width={skeletonWidth(index + 2)} />
      ))}
      <FolderRow indent={12} width="42%" />
      {[0, 1, 2, 3, 4, 5].map((index) => (
        <FolderRow key={index} indent={28} width={skeletonWidth(index + 5)} />
      ))}
    </div>
  );
}
