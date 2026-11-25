import { useRegions } from "../../level/map-graph/map-graph-data";
import { regionFeatures } from "./record-geo";

// Whether the Analyse tab's maps have anything to draw: area maps need the
// record's regions. Without them a map would be a bare basemap, so map views
// are greyed out instead.

export const NO_REGIONS = "No map: this record has no bus regions to draw.";

/** False only once the regions have loaded and there are none: while they load, or if they fail, a map isn't ruled out. */
export function useHasMapRegions(): boolean {
  const regions = useRegions();
  return regions.status !== "ready" || regionFeatures(regions.data).length > 0;
}
