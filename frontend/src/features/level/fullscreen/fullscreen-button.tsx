// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { LuMaximize2, LuMinimize2 } from "react-icons/lu";
import { useLevelStore } from "../level-store";
import { useInFullscreen, type ExpandableBlock } from "./fullscreen-context";

// A block's full screen button, in its own bar: opens the block in the full
// screen dialog (BlockFullscreen), or in the dialog, closes it.

export function FullscreenButton({ block }: { block: ExpandableBlock }) {
  const inDialog = useInFullscreen();
  const setExpanded = useLevelStore((s) => s.setExpandedBlock);
  const label = inDialog ? "Exit full screen" : "Full screen";
  const Icon = inDialog ? LuMinimize2 : LuMaximize2;
  return (
    <button
      type="button"
      data-fullscreen-toggle={inDialog ? undefined : block}
      aria-label={label}
      title={inDialog ? `${label} (Esc)` : label}
      onClick={() => setExpanded(inDialog ? null : block)}
      className="border-surface-600 text-surface-300 hover:border-surface-500 hover:text-surface-100 focus-visible:border-accent-500 flex h-7 w-7 shrink-0 items-center justify-center rounded border outline-none"
    >
      <Icon size={13} />
    </button>
  );
}
