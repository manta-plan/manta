import { FullscreenButton } from "../fullscreen/fullscreen-button";
import { useInFullscreen } from "../fullscreen/fullscreen-context";
import { Segmented } from "../../../components/segmented";
import { LuMap, LuNetwork, LuX } from "react-icons/lu";
import { isLocationLevel } from "../level";
import { useLevelPage } from "../level-page-context";
import { useLevelStore, type MapGraphTab } from "../level-store";
import { LevelGraph } from "./graph/level-graph";
import { LevelMap } from "./map/level-map";
import { useMapSummaryLine } from "./map/map-summary";

// Map & graph, beside the table: the Map, or the Graph of buses (in
// location mode and on a single entity), with a close button.

const GRAPH_OFF = "The graph shows buses. Open a single entity or the Locations tree to use it.";

export function MapGraph() {
  const { level } = useLevelPage();
  const panel = useLevelStore((s) => s.mapGraphTab);
  const setPanel = useLevelStore((s) => s.setMapGraphTab);
  const setOpen = useLevelStore((s) => s.setMapGraphOpen);
  const inDialog = useInFullscreen();
  const graphOn = isLocationLevel(level) || level.kind === "entity";
  const shown: MapGraphTab = panel === "graph" && graphOn ? "graph" : "map";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-surface-700 flex h-9 shrink-0 items-center gap-2 border-b px-2">
        <Segmented
          kind="tabs"
          ariaLabel="Map or graph"
          idPrefix="map-graph-tab"
          panelId="map-graph-body"
          value={shown}
          onChange={setPanel}
          options={[
            { value: "map", label: "Map", icon: LuMap },
            {
              value: "graph",
              label: "Graph",
              icon: LuNetwork,
              disabled: !graphOn,
              title: graphOn ? undefined : GRAPH_OFF,
            },
          ]}
        />
        {/* Above the map, not over it: what the level highlights. */}
        {shown === "map" ? <MapSummaryNote /> : <HeaderNote text={graphNote(level)} />}
        <FullscreenButton block="map-graph" />
        {/* Closing the block only makes sense in place; full screen has Exit. */}
        {!inDialog && (
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close the map and graph"
            title="Close"
            className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 focus-visible:ring-accent-500 rounded p-1 outline-none focus-visible:ring-1"
          >
            <LuX size={14} />
          </button>
        )}
      </div>
      <div
        id="map-graph-body"
        role="tabpanel"
        aria-labelledby={`map-graph-tab-${shown}`}
        className="relative min-h-0 flex-1"
      >
        {shown === "map" ? <LevelMap /> : <LevelGraph />}
      </div>
    </div>
  );
}

function HeaderNote({ text }: { text: string | null }) {
  return (
    <span
      title={text ?? undefined}
      className="text-surface-300 min-w-0 flex-1 truncate text-[11px]"
    >
      {text}
    </span>
  );
}

// Its own component, so the map's reads run only while the map shows.
function MapSummaryNote() {
  return <HeaderNote text={useMapSummaryLine()} />;
}

function graphNote(level: ReturnType<typeof useLevelPage>["level"]): string {
  switch (level.kind) {
    case "all-locations":
      return "All buses, placed by location";
    case "location":
      return `Buses at ${level.location}`;
    case "bus":
      return `Buses at ${level.location ?? level.bus}`;
    default:
      return "Buses around this entity";
  }
}
