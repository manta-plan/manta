// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useMemo } from "react";
import { useRegions, type RegionRow } from "../../level/map-graph/map-graph-data";
import type { WktPolygonal } from "../../project/lib/wkt";

// GeoJSON for the map widgets, from the record's bus regions.

export interface RegionFeature {
  type: "Feature";
  // `name` is the region's location: what map clicks and result values key
  // on. Some locations have two regions.
  properties: { name: string; entity: string };
  geometry: WktPolygonal;
}

export function regionFeatures(regions: RegionRow[]): RegionFeature[] {
  return regions.flatMap((region) =>
    region.location
      ? [
          {
            type: "Feature" as const,
            properties: { name: region.location, entity: region.entity },
            geometry: region.geometry,
          },
        ]
      : [],
  );
}

/** The record's region shapes; empty while they load. */
export function useRegionFeatures(): RegionFeature[] {
  const regions = useRegions();
  return useMemo(() => (regions.status === "ready" ? regionFeatures(regions.data) : []), [regions]);
}
