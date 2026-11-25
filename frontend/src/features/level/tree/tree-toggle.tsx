// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { NodeApi } from "react-arborist";
import { LuChevronDown, LuChevronRight } from "react-icons/lu";

/**
 * A record tree row's fold button: the only thing that collapses a row (a
 * click on the row opens what it names). Out of the tab order: the tree's
 * arrow keys fold, Enter opens. A leaf gets the same width, empty.
 */
export function TreeToggle<T>({ node }: { node: NodeApi<T> }) {
  if (!node.isInternal) return <span className="w-5 shrink-0" />;
  const Icon = node.isOpen ? LuChevronDown : LuChevronRight;
  return (
    <button
      type="button"
      tabIndex={-1}
      aria-label={node.isOpen ? "Collapse" : "Expand"}
      aria-expanded={node.isOpen}
      onClick={(event) => {
        event.stopPropagation();
        node.toggle();
      }}
      className="text-surface-400 hover:bg-surface-600 hover:text-surface-50 -ml-1 grid h-5 w-5 shrink-0 cursor-pointer place-items-center rounded outline-none"
    >
      <Icon size={12} />
    </button>
  );
}
