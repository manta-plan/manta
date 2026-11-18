import type { MapLayerStyle } from "../../data/map-layers";
import type { ProjectStoreSet, BasemapId, CursorPosition, ToolId, ViewState } from "../types";

// The theme the home store keeps (features/home/store.ts); the vector basemap
// starts on its variant. Following a later toggle is up to whoever toggles.
const themeStorageKey = "manta-plan-theme";

function initialBasemap(): BasemapId {
  try {
    return window.localStorage.getItem(themeStorageKey) === "light"
      ? "vector-light"
      : "vector-dark";
  } catch {
    return "vector-dark";
  }
}

export function createMapToolSlice(set: ProjectStoreSet) {
  return {
    activeTool: "select" as ToolId,
    setActiveTool: (tool: ToolId) => set({ activeTool: tool }),

    basemap: initialBasemap(),
    setBasemap: (basemap: BasemapId) => set({ basemap }),

    // Overrides only; each layer's defaults live in mapLayers.ts, since the
    // link layers depend on the record's carriers.
    mapLayerVisibility: {} as Record<string, boolean>,
    setMapLayerVisible: (id: string, visible: boolean) =>
      set((state) => ({ mapLayerVisibility: { ...state.mapLayerVisibility, [id]: visible } })),

    mapLayerStyle: {} as Record<string, Partial<MapLayerStyle>>,
    setMapLayerColor: (id: string, color: string) =>
      set((state) => ({
        mapLayerStyle: { ...state.mapLayerStyle, [id]: { ...state.mapLayerStyle[id], color } },
      })),
    setMapLayerOpacity: (id: string, opacity: number) =>
      set((state) => ({
        mapLayerStyle: { ...state.mapLayerStyle, [id]: { ...state.mapLayerStyle[id], opacity } },
      })),
    resetMapLayerStyle: (id: string) =>
      set((state) => {
        const { [id]: _reset, ...mapLayerStyle } = state.mapLayerStyle;
        return { mapLayerStyle };
      }),

    viewState: {
      longitude: 4.5,
      latitude: 50.6,
      zoom: 7.7,
      bearing: 0,
      pitch: 0,
    } satisfies ViewState,
    setViewState: (v: ViewState) => set({ viewState: v }),
    mapFocus: null,
    focusMap: (points: [number, number][]) => set({ mapFocus: { points, at: Date.now() } }),

    cursorPosition: null,
    setCursorPosition: (c: CursorPosition | null) => set({ cursorPosition: c }),
  };
}
