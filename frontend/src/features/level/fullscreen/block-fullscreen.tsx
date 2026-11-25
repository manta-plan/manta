// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState, type ComponentType } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, type Transition } from "motion/react";
import { LevelChartDrawer } from "../chart/level-chart-drawer";
import { useLevelStore } from "../level-store";
import { MapGraph } from "../map-graph/map-graph";
import { LevelTable } from "../table/level-table";
import { BLOCK_LABELS, InFullscreen, type ExpandableBlock } from "./fullscreen-context";

// A block full screen (the table, Map & graph or the chart drawer): a wide
// dialog over the page. Each block is in one place at a time (its slot on the
// page, or the dialog) and its box is one shared element (the same layoutId),
// so it grows out of the page into the dialog and shrinks back into place on
// close. The map in full screen is a new instance, so it opens zoomed to the
// level.

const SPRING: Transition = { type: "spring", bounce: 0.12, duration: 0.45 };

const BLOCKS: Record<ExpandableBlock, ComponentType> = {
  table: LevelTable,
  "map-graph": MapGraph,
  chart: LevelChartDrawer,
};

const layoutId = (block: ExpandableBlock) => `level-block-${block}`;

/** A block's place on the page: the block, or while it's full screen, the space it'll return to (same height, so nothing below moves). */
export function BlockSlot({ block }: { block: ExpandableBlock }) {
  const expanded = useLevelStore((s) => s.expandedBlock === block);
  const Block = BLOCKS[block];
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | null>(null);
  // The block's height while in place: what the placeholder holds.
  useEffect(() => {
    const element = box.current;
    if (expanded || !element) return;
    const observer = new ResizeObserver(() => setHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, [expanded]);
  if (expanded) {
    return (
      <div
        aria-hidden
        className="bg-surface-950/40 h-full"
        style={{ minHeight: height ?? undefined }}
      />
    );
  }
  return (
    <motion.div ref={box} layoutId={layoutId(block)} transition={SPRING} className="h-full">
      {/* Counter-scales the content while the box animates, so text doesn't stretch. */}
      <motion.div layout transition={SPRING} className="h-full">
        <Block />
      </motion.div>
    </motion.div>
  );
}

/** The dialog a block grows into. Esc, the backdrop or the block's button close it. */
export function BlockFullscreenDialog() {
  const expanded = useLevelStore((s) => s.expandedBlock);
  const setExpanded = useLevelStore((s) => s.setExpandedBlock);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!expanded) return;
    const opener = document.activeElement as HTMLElement | null;
    box.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      // A popover inside (a column menu, a dropdown) closes first.
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !document.querySelector("[data-popup-open]")
      ) {
        setExpanded(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      // Back to the button that opened it, once the block is back in place.
      requestAnimationFrame(() =>
        (
          document.querySelector<HTMLElement>(`[data-fullscreen-toggle="${expanded}"]`) ?? opener
        )?.focus(),
      );
    };
  }, [expanded, setExpanded]);

  const Block = expanded ? BLOCKS[expanded] : null;
  return createPortal(
    <AnimatePresence>
      {expanded && Block && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setExpanded(null)}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]"
          />
          <motion.div
            key={expanded}
            ref={box}
            layoutId={layoutId(expanded)}
            transition={SPRING}
            role="dialog"
            aria-modal="true"
            aria-label={`${BLOCK_LABELS[expanded]}, full screen`}
            tabIndex={-1}
            style={{ borderRadius: 8 }}
            className="border-surface-600 bg-surface-900 fixed inset-x-[3vw] inset-y-[4vh] z-40 overflow-hidden border shadow-2xl shadow-black/60 outline-none"
          >
            <motion.div layout transition={SPRING} className="h-full overflow-auto">
              <InFullscreen.Provider value>
                <Block />
              </InFullscreen.Provider>
            </motion.div>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body,
  );
}
