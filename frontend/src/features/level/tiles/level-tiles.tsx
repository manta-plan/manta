import { useLevelPage } from "../level-page-context";
import { useLevelStore } from "../level-store";
import { Tile } from "./tile";
import { levelTiles } from "./tiles-by-level";
import { useTileInputs, useTileResults } from "./tile-queries";

// The level's stat tiles: one read of the inputs (and on Inspect one of the
// run result), then the tiles the level shows (tilesByLevel).

export function LevelTiles() {
  const { level, stage, result, scope, openLevel } = useLevelPage();
  const timeWindow = useLevelStore((s) => s.timeWindow);
  const results = stage === "inspect" && result !== null;
  const inputs = useTileInputs(scope, results);
  const runResults = useTileResults(scope, results);
  const tiles = levelTiles({
    level,
    results,
    stage,
    period: scope?.period ?? "",
    windowLabel: timeWindow?.label ?? "full span",
    inputs,
    runResults,
    open: openLevel,
  });
  return (
    <section
      aria-label="Figures"
      className="grid shrink-0 grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-2"
    >
      {tiles.map((spec) => (
        <Tile key={spec.key} spec={spec} />
      ))}
    </section>
  );
}
