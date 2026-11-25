// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { NodeApi } from "react-arborist";

/**
 * A record tree row's click (or Enter): opens what the row names, if it
 * names something to open, and unfolds it so its children come next (never
 * folds: that's the chevron's). A row with nothing to open (a folder)
 * folds and unfolds.
 */
export function activateTreeRow<T>(node: NodeApi<T>, open: (() => void) | null) {
  if (open) {
    open();
    if (node.isInternal && !node.isOpen) node.open();
  } else if (node.isInternal) node.toggle();
}
