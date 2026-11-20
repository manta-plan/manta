import { area } from "@turf/area";
import { length } from "@turf/length";
import type { Feature, FeatureCollection, LineString, Point, Polygon } from "geojson";

export type MeasureMode = "distance" | "area";

export const MEASURE_FILL_LAYER_ID = "measure-fill";
export const MEASURE_LINE_LAYER_ID = "measure-line";
export const MEASURE_VERTEX_LAYER_ID = "measure-vertices";
export const MEASURE_LAYER_IDS = [
  MEASURE_FILL_LAYER_ID,
  MEASURE_LINE_LAYER_ID,
  MEASURE_VERTEX_LAYER_ID,
];

export type LngLat = [number, number];

export interface Measurement {
  /** Path length in meters; for area mode this is the closed perimeter. */
  distance: number;
  /** Enclosed area in square meters; 0 until there are 3 vertices. */
  area: number;
}

function lineFeature(coordinates: LngLat[]): Feature<LineString> {
  return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } };
}

function polygonFeature(points: LngLat[]): Feature<Polygon> {
  return {
    type: "Feature",
    properties: {},
    geometry: { type: "Polygon", coordinates: [[...points, points[0]]] },
  };
}

/** Distances are geodesic (great-circle), so they hold up at continental scale. */
export function measure(points: LngLat[], mode: MeasureMode): Measurement {
  if (points.length < 2) return { distance: 0, area: 0 };
  const closed = mode === "area" && points.length >= 3;
  const path = closed ? [...points, points[0]] : points;
  return {
    distance: length(lineFeature(path), { units: "kilometers" }) * 1000,
    area: closed ? area(polygonFeature(points)) : 0,
  };
}

export function measureGeometry(
  points: LngLat[],
  mode: MeasureMode,
): FeatureCollection<LineString | Polygon | Point> {
  const features: Feature<LineString | Polygon | Point>[] = points.map((coordinates) => ({
    type: "Feature",
    properties: {},
    geometry: { type: "Point", coordinates },
  }));
  if (mode === "area" && points.length >= 3) features.unshift(polygonFeature(points));
  else if (points.length >= 2) features.unshift(lineFeature(points));
  return { type: "FeatureCollection", features };
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  const km = meters / 1000;
  return `${km.toLocaleString(undefined, { maximumFractionDigits: km < 10 ? 2 : 1 })} km`;
}

export function formatArea(squareMeters: number): string {
  if (squareMeters < 10_000) return `${Math.round(squareMeters).toLocaleString()} m²`;
  const km2 = squareMeters / 1_000_000;
  return `${km2.toLocaleString(undefined, { maximumFractionDigits: km2 < 10 ? 2 : 1 })} km²`;
}
