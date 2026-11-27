// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { BusRow } from "../map-graph-data";

// Points and boxes for the map, in lon/lat.

export type LngLat = [number, number];
export type Bounds = [LngLat, LngLat];

/** Each location's point: its own bus (named after it), else its first. */
export function locationPoints(buses: BusRow[]): Map<string, LngLat> {
  const points = new Map<string, LngLat>();
  for (const bus of buses) {
    if (!Number.isFinite(bus.x) || !Number.isFinite(bus.y)) continue;
    if (bus.bus === bus.location || !points.has(bus.location))
      points.set(bus.location, [bus.x, bus.y]);
  }
  return points;
}

export function boundsOf(points: Iterable<LngLat>): Bounds | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const [x, y] of points) {
    west = Math.min(west, x);
    east = Math.max(east, x);
    south = Math.min(south, y);
    north = Math.max(north, y);
  }
  return Number.isFinite(west)
    ? [
        [west, south],
        [east, north],
      ]
    : null;
}

/** The box grown by `share` of its larger side on every side (and at least `min` degrees across). */
export function padBounds(
  [[west, south], [east, north]]: Bounds,
  share: number,
  min = 0.08,
): Bounds {
  const width = Math.max(min, east - west);
  const height = Math.max(min, north - south);
  const pad = Math.max(width, height) * share;
  const cx = (west + east) / 2;
  const cy = (south + north) / 2;
  return [
    [cx - width / 2 - pad, cy - height / 2 - pad],
    [cx + width / 2 + pad, cy + height / 2 + pad],
  ];
}
