// Minimal WKT parsing for the two geometry shapes topology.json actually
// contains (LINESTRING for backdrop lines/links/transformers) — not a
// general WKT library, just enough for this dataset.

export function parseWktLineString(wkt: string): [number, number][] {
  const match = /LINESTRING\s*\(([^)]+)\)/i.exec(wkt);
  if (!match) return [];
  return match[1]
    .split(",")
    .map((pair) => pair.trim().split(/\s+/).map(Number))
    .filter(
      (coord): coord is [number, number] =>
        coord.length === 2 && coord.every((n) => Number.isFinite(n)),
    );
}

export type WktPolygonal =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };

const WKT_NUMBER = String.raw`-?\d+(?:\.\d+)?(?:e[-+]?\d+)?`;
const WKT_PAIR = new RegExp(String.raw`(${WKT_NUMBER})\s+(${WKT_NUMBER})`, "gi");

// POLYGON and MULTIPOLYGON (holes included), as GeoJSON geometries: the WKT
// nesting is already GeoJSON's once its parentheses become arrays.
export function parseWktPolygonal(wkt: string): WktPolygonal | null {
  const match = /^\s*(MULTIPOLYGON|POLYGON)\s*(\(.*\))\s*$/is.exec(wkt);
  if (!match) return null;
  try {
    const coordinates: unknown = JSON.parse(
      match[2].replace(WKT_PAIR, "[$1,$2]").replaceAll("(", "[").replaceAll(")", "]"),
    );
    return match[1].toUpperCase() === "POLYGON"
      ? { type: "Polygon", coordinates: coordinates as number[][][] }
      : { type: "MultiPolygon", coordinates: coordinates as number[][][][] };
  } catch {
    return null;
  }
}
