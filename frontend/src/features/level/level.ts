import { componentOfPageId, componentPageId } from "./component-page";
import { entityOfPageId, entityPageId } from "./entity-page";

// A level: what the record tree points at and every part of the page
// follows (tiles, table, map or graph, chart drawer). Two roots: All entities
// (Entities › type › carrier › entity) and All locations (Locations ›
// location › bus › entity). The page's address names it; no id is All
// entities.

export type Level =
  | { kind: "all-entities" }
  | { kind: "component"; ctype: string }
  | { kind: "carrier"; ctype: string; carrier: string }
  | { kind: "entity"; entity: string }
  | { kind: "all-locations" }
  | { kind: "location"; location: string }
  | { kind: "bus"; bus: string; location: string | null };

export type LevelKind = Level["kind"];

export const ALL_ENTITIES: Level = { kind: "all-entities" };
export const ALL_LOCATIONS: Level = { kind: "all-locations" };

const LOCATIONS_ID = "locations";
const LOCATION_PREFIX = "location:";
const BUS_PREFIX = "bus:";

const decode = (text: string) => {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
};

/** The level's page id (the address after /build/ or /inspect/); null for All entities. */
export function levelPageId(level: Level): string | null {
  switch (level.kind) {
    case "all-entities":
      return null;
    case "component":
      return componentPageId(level.ctype);
    case "carrier":
      return componentPageId(level.ctype, level.carrier);
    case "entity":
      return entityPageId(level.entity);
    case "all-locations":
      return LOCATIONS_ID;
    case "location":
      return `${LOCATION_PREFIX}${encodeURIComponent(level.location)}`;
    case "bus":
      return `${BUS_PREFIX}${encodeURIComponent(level.bus)}${level.location === null ? "" : `@${encodeURIComponent(level.location)}`}`;
  }
}

/** The level a page id names, or null when it names none (a comparison, a view). No id is All entities. */
export function levelOfPageId(id: string | null | undefined): Level | null {
  if (!id) return ALL_ENTITIES;
  if (id === LOCATIONS_ID) return ALL_LOCATIONS;
  if (id.startsWith(LOCATION_PREFIX))
    return { kind: "location", location: decode(id.slice(LOCATION_PREFIX.length)) };
  if (id.startsWith(BUS_PREFIX)) {
    const [bus, location] = id.slice(BUS_PREFIX.length).split("@");
    return {
      kind: "bus",
      bus: decode(bus),
      location: location === undefined ? null : decode(location),
    };
  }
  const entity = entityOfPageId(id);
  if (entity) return { kind: "entity", entity };
  const subject = componentOfPageId(id);
  if (subject)
    return subject.carrier === null
      ? { kind: "component", ctype: subject.ctype }
      : { kind: "carrier", ctype: subject.ctype, carrier: subject.carrier };
  return null;
}

/** Whether the level is under All locations (location mode: the graph is on). */
export function isLocationLevel(level: Level): boolean {
  return level.kind === "all-locations" || level.kind === "location" || level.kind === "bus";
}

/** Whether the level is a group of entities (statistics are on), not one entity. */
export function isGroupLevel(level: Level): boolean {
  return level.kind !== "entity";
}

export function sameLevel(a: Level, b: Level): boolean {
  return levelPageId(a) === levelPageId(b);
}

/**
 * What the level filters entities by, for the `members` fragment: null is
 * "any". An entity level has the entity only; its ctype etc. come from the
 * row.
 */
export interface LevelFilter {
  ctype: string | null;
  carrier: string | null;
  location: string | null;
  bus: string | null;
  entity: string | null;
}

export function levelFilter(level: Level): LevelFilter {
  const none: LevelFilter = { ctype: null, carrier: null, location: null, bus: null, entity: null };
  switch (level.kind) {
    case "all-entities":
    case "all-locations":
      return none;
    case "component":
      return { ...none, ctype: level.ctype };
    case "carrier":
      return { ...none, ctype: level.ctype, carrier: level.carrier };
    case "entity":
      return { ...none, entity: level.entity };
    case "location":
      return { ...none, location: level.location };
    case "bus":
      return { ...none, bus: level.bus };
  }
}
