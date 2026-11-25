import { createContext, useContext } from "react";
import type { InspectResult } from "../project/lib/record-results";
import type { Level } from "./level";
import type { LevelQueryScope } from "./level-sql";

// What every part of a level's page reads: the level, the stage (Build edits
// a scenario's inputs, Inspect reads a run's results too), the result shown
// on Inspect, and the query scope (null until the periods are read).

export interface LevelPageValue {
  level: Level;
  stage: "build" | "inspect";
  /** The run result shown, on Inspect; null on Build or with a scenario shown. */
  result: InspectResult | null;
  scope: LevelQueryScope | null;
  /** Opens another level (navigates; the tree follows). */
  openLevel: (level: Level) => void;
}

export const LevelPageContext = createContext<LevelPageValue | null>(null);

export function useLevelPage(): LevelPageValue {
  const value = useContext(LevelPageContext);
  if (!value) throw new Error("useLevelPage outside a level page");
  return value;
}
