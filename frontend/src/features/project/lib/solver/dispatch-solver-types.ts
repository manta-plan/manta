// What a stored run records about a solve. The in-browser solver that
// produced these read the browser's project database and is gone; runs keep
// the shapes so saved runs still render until runs move to the server.

export type SolveProgressStage = "loading-runtime" | "loading-packages" | "solving" | "done";

export interface SolveResultGenerator {
  id: string;
  existingMw: number;
  builtMw: number;
  addedMw: number;
}
