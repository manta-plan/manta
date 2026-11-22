import { create } from "zustand";
import { useAppStore } from "../../home/store";
import type { ProjectState } from "./types";
import { createCurrentProjectSlice } from "./slices/current-project-slice";
import { createDrawerSlice } from "./slices/drawer-slice";
import { createMapToolSlice } from "./slices/map-tool-slice";
import { createRecordSlice } from "./slices/record-slice";
import { createScenarioRunReportSlice } from "./slices/scenario-run-report-slice";

export type {
  BasemapId,
  CreateInspectionInput,
  CreateReportInput,
  CreateRunInput,
  CreateScenarioInput,
  CreateScenarioMutationInput,
  CreateScenarioDirectMutationInput,
  NewInspectionInput,
  ProjectState,
  RecordItem,
  Resolution,
  TableDrawerContent,
  ScenarioSelection,
  ToolId,
  UtilityDrawerFlow,
} from "./types";

// The state of the project workspace. The project list, the theme and the new
// and rename project drawers belong to the home store (features/home/store.ts).
export const useProjectStore = create<ProjectState>((set, get) => ({
  ...createCurrentProjectSlice(set),
  ...createMapToolSlice(set),
  ...createDrawerSlice(set),
  ...createRecordSlice(set, get),
  ...createScenarioRunReportSlice(set, get),
}));

// A vector basemap follows the theme the home store keeps; satellite imagery has
// no light/dark variant, so it stays put when the theme toggles.
useAppStore.subscribe((state, previous) => {
  if (state.theme === previous.theme) return;
  const { basemap, setBasemap } = useProjectStore.getState();
  if (basemap !== "satellite") setBasemap(state.theme === "dark" ? "vector-dark" : "vector-light");
});
