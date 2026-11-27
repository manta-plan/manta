import { levelPageId, type Level } from "../level";
import {
  busNodeId,
  carrierNodeId,
  ctypeNodeId,
  findTreeNode,
  locationNodeId,
  type TreeNode,
} from "./tree-nodes";

// Which tree row shows the open level, so the tree can unfold to it after a
// pick in the table, on the map or in search. Folders load their children on
// first open, so a row deep in the tree can take a load (or two) first.

/** An entity's type and carrier: where it sits under Entities. */
export interface EntityPlace {
  ctype: string;
  carrier: string | null;
}

export type RevealStep =
  /** Nothing (more) to unfold to. */
  | { kind: "done" }
  /** The entity's place is still being read. */
  | { kind: "wait" }
  /** Load this folder's children, then plan again. */
  | { kind: "load"; id: string }
  /** Unfold this row's parents and scroll to it. */
  | { kind: "reveal"; id: string };

const DONE: RevealStep = { kind: "done" };

/** A row that exists, revealed; else done. */
function revealIf(tree: TreeNode[], id: string): RevealStep {
  return findTreeNode(tree, id) ? { kind: "reveal", id } : DONE;
}

/**
 * The next step to show the level's row. `loaded` is the folders' children
 * read so far; `place` is the entity's type and carrier (undefined while
 * read, null when unknown). An entity is shown under Entities: its row, or
 * the folder's "n more in the table" when the list stops before it.
 */
export function revealStep(
  level: Level | null,
  tree: TreeNode[],
  loaded: Record<string, TreeNode[]>,
  place: EntityPlace | null | undefined,
): RevealStep {
  switch (level?.kind) {
    case "component":
      return revealIf(tree, ctypeNodeId(level.ctype));
    case "carrier":
      return revealIf(tree, carrierNodeId(level.ctype, level.carrier));
    case "location":
      return revealIf(tree, locationNodeId(level.location));
    case "bus": {
      if (level.location === null) return DONE;
      const id = busNodeId(level.bus, level.location);
      if (findTreeNode(tree, id)) return { kind: "reveal", id };
      const location = locationNodeId(level.location);
      // A location's buses arrive when it loads.
      return findTreeNode(tree, location) && !loaded[location]
        ? { kind: "load", id: location }
        : DONE;
    }
    case "entity": {
      if (place === undefined) return { kind: "wait" };
      if (place === null) return DONE;
      // A type with only carrier-less entities lists them itself.
      const folder =
        findTreeNode(tree, carrierNodeId(place.ctype, place.carrier)) ??
        findTreeNode(tree, ctypeNodeId(place.ctype));
      if (!folder) return DONE;
      if (!folder.lazy) return { kind: "reveal", id: folder.id };
      const children = loaded[folder.id];
      if (!children) return { kind: "load", id: folder.id };
      const row =
        findTreeNode(children, `${folder.id}/${level.entity}`) ??
        findTreeNode(children, `${folder.id}/more`) ??
        children[0];
      return { kind: "reveal", id: row?.id ?? folder.id };
    }
    default:
      return DONE;
  }
}

/**
 * A row on show (every folder above it open) that is the page's level, if
 * any: a pick in the tree itself, say under Locations, stays where it is
 * instead of the tree unfolding Entities to another row of it.
 */
export function shownRowOf(
  rows: readonly { id: string; data: TreeNode }[],
  pageId: string | null,
): string | null {
  const row = rows.find(
    ({ data }) =>
      data.kind !== "more" && data.level !== undefined && levelPageId(data.level) === pageId,
  );
  return row?.id ?? null;
}
