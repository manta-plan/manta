import { parseWktPolygonal, type WktPolygonal } from "./wkt";
import { NODAL, type LoadedRecord, type Resolution } from "../store/types";

// GeoJSON for the map, from the loaded record.

export interface RegionFeature {
  type: "Feature";
  // `name` is the region's location (or zone): what map clicks and result
  // values key on. Some locations have two regions.
  properties: { name: string; entity: string; zone: string | null };
  geometry: WktPolygonal;
}

export interface PlaceFeature {
  type: "Feature";
  properties: { name: string; buses: number; locations: number };
  geometry: { type: "Point"; coordinates: [number, number] };
}

export interface BranchFeature {
  type: "Feature";
  properties: { id: string; ctype: string; carrier: string; count: number; entities: string[] };
  geometry: { type: "LineString"; coordinates: [number, number][] };
}

// location → zone at a zone level; empty at nodal resolution.
export function zoneOf(record: LoadedRecord, resolution: Resolution): Map<string, string> {
  if (resolution === NODAL) return new Map();
  return new Map(
    record.zones
      .filter((zone) => zone.level === resolution)
      .map((zone) => [zone.location, zone.zone]),
  );
}

// The zone levels worth offering: those that actually group locations
// (busmap_all keeps one zone per location, which is just nodal).
export function zoneLevels(record: LoadedRecord): { level: string; zones: number }[] {
  const zonesByLevel = new Map<string, Set<string>>();
  for (const { level, zone } of record.zones)
    zonesByLevel.set(level, (zonesByLevel.get(level) ?? new Set()).add(zone));
  return [...zonesByLevel]
    .map(([level, zones]) => ({ level, zones: zones.size }))
    .filter(({ zones }) => zones < record.locations.length)
    .sort((a, b) => a.zones - b.zones);
}

export function regionFeatures(
  record: LoadedRecord | null,
  resolution: Resolution = NODAL,
): RegionFeature[] {
  if (!record) return [];
  const zones = zoneOf(record, resolution);
  return record.regions.flatMap((region) => {
    const geometry = parseWktPolygonal(region.wkt);
    if (!geometry) return [];
    const location = region.location ?? region.bus ?? region.entity;
    const zone = zones.get(location) ?? null;
    return [
      {
        type: "Feature" as const,
        properties: { name: zone ?? location, entity: region.entity, zone },
        geometry,
      },
    ];
  });
}

// One point per location, or per zone at the centre of its locations.
export function placeFeatures(record: LoadedRecord, resolution: Resolution): PlaceFeature[] {
  const zones = zoneOf(record, resolution);
  const places = new Map<string, { x: number; y: number; buses: number; locations: number }>();
  for (const location of record.locations) {
    const name = zones.get(location.location) ?? location.location;
    const place = places.get(name) ?? { x: 0, y: 0, buses: 0, locations: 0 };
    place.x += location.x;
    place.y += location.y;
    place.buses += location.buses;
    place.locations += 1;
    places.set(name, place);
  }
  return [...places].map(([name, place]) => ({
    type: "Feature",
    properties: { name, buses: place.buses, locations: place.locations },
    geometry: {
      type: "Point",
      coordinates: [place.x / place.locations, place.y / place.locations],
    },
  }));
}

// Which locations make up a place (a location, or a zone's locations).
export function placeLocations(
  record: LoadedRecord,
  resolution: Resolution,
  place: string,
): string[] {
  if (resolution === NODAL) return [place];
  return record.zones
    .filter((zone) => zone.level === resolution && zone.zone === place)
    .map((zone) => zone.location);
}

// Branches between places, one line per place pair, ctype and carrier, so
// parallel lines (or a zone's many lines) draw once with a count.
export function branchFeatures(record: LoadedRecord, resolution: Resolution): BranchFeature[] {
  const zones = zoneOf(record, resolution);
  const centres = new Map(
    placeFeatures(record, resolution).map((place) => [
      place.properties.name,
      place.geometry.coordinates,
    ]),
  );
  const groups = new Map<string, BranchFeature>();
  for (const branch of record.branches) {
    const from = zones.get(branch.location0) ?? branch.location0;
    const to = zones.get(branch.location1) ?? branch.location1;
    if (from === to) continue;
    const [a, b] = from < to ? [from, to] : [to, from];
    const carrier = branch.carrier ?? "";
    const id = `${branch.ctype}|${carrier}|${a}|${b}`;
    const start = centres.get(a);
    const end = centres.get(b);
    if (!start || !end) continue;
    const group = groups.get(id) ?? {
      type: "Feature" as const,
      properties: { id, ctype: branch.ctype, carrier, count: 0, entities: [] },
      geometry: { type: "LineString" as const, coordinates: [start, end] },
    };
    if (!group.properties.entities.includes(branch.entity)) {
      group.properties.entities.push(branch.entity);
      group.properties.count += 1;
    }
    groups.set(id, group);
  }
  return [...groups.values()];
}
