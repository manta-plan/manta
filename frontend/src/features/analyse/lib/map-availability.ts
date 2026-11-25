import { useRegionFeatures } from "./record-geo";

// Whether the Analyse tab's maps have anything to draw: area maps need the
// record's regions. Without them a map would be a bare basemap, so map views
// are greyed out instead.

export const NO_REGIONS = "No map: this record has no bus regions to draw.";

export function useHasMapRegions(): boolean {
  return useRegionFeatures().length > 0;
}
