import type { ComponentType } from "react";
import { LevelChartDrawer } from "../chart/level-chart-drawer";
import { MapGraph } from "../map-graph/map-graph";
import { LevelTable } from "../table/level-table";
import type { ExpandableBlock } from "./fullscreen-context";

// STUB: replaced by the real port of baby-manta's fullscreen/BlockFullscreen.tsx
// in phase B (BlockSlot with the motion shared layout, the dialog). For now a
// slot just renders its block in place and there is no full screen dialog.

const BLOCKS: Record<ExpandableBlock, ComponentType> = {
  table: LevelTable,
  "map-graph": MapGraph,
  chart: LevelChartDrawer,
};

/** A block's place on the page. */
export function BlockSlot({ block }: { block: ExpandableBlock }) {
  const Block = BLOCKS[block];
  return (
    <div className="h-full">
      <Block />
    </div>
  );
}

/** The dialog a block grows into (stub: renders nothing). */
export function BlockFullscreenDialog() {
  return null;
}
