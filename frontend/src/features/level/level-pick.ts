import type { Level } from "./level";

// Picks across the two trees (Entities and Locations). The level open is the
// context: a pick from the other tree, in the table, on the map or in the
// graph, narrows it instead of replacing it ("Generators at BE0 0", or
// "BE0 0 among Generators"). A pick from the context's own tree, an entity
// or a root opens that level, as before. The tree beside the page always
// opens what it names.

/** A level that can narrow a level of the other tree. */
export type CrossFilter = Extract<Level, { kind: "component" | "carrier" | "location" | "bus" }>;

type Tree = "entities" | "locations";

/** The tree a group level sits under; null for the roots and single entities (they never combine). */
export function treeOf(level: Level): Tree | null {
  switch (level.kind) {
    case "component":
    case "carrier":
      return "entities";
    case "location":
    case "bus":
      return "locations";
    default:
      return null;
  }
}

function isCrossFilter(level: Level): level is CrossFilter {
  return treeOf(level) !== null;
}

export type PickOutcome = { kind: "open"; level: Level } | { kind: "filter"; filter: CrossFilter };

/** What picking `pick` does on `context`'s page: open it, or keep the page and filter by it. */
export function pickLevel(context: Level, pick: Level): PickOutcome {
  const here = treeOf(context);
  const there = treeOf(pick);
  if (here !== null && there !== null && here !== there && isCrossFilter(pick))
    return { kind: "filter", filter: pick };
  return { kind: "open", level: pick };
}

/** The filter in words, for its chip: "Generator", "Generator · Solar", "BE0 0", "Bus BE0 0 H2". */
export function crossFilterLabel(
  filter: CrossFilter,
  carrierName: (carrier: string) => string = (carrier) => carrier,
): string {
  switch (filter.kind) {
    case "component":
      return filter.ctype;
    case "carrier":
      return `${filter.ctype} · ${carrierName(filter.carrier)}`;
    case "location":
      return filter.location;
    case "bus":
      return `Bus ${filter.bus}`;
  }
}
