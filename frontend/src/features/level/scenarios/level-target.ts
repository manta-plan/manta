import { useShownData } from "../../project/lib/record-data";
import type { DraftChangeTarget } from "../../project/lib/draft-scenarios";
import type { Level } from "../level";
import { loadEntityPlace } from "./change-sql";

// What a change made from a level applies to: the entity at an entity level
// (once its type and place are read), else the entities the level groups.
// Levels that name no component type default to Generator.

export const DEFAULT_CTYPE = "Generator";

/** The filter a group level gives; an entity level gives none (see useLevelChangeTarget). */
export function levelFilterTarget(
  level: Level,
): Extract<DraftChangeTarget, { kind: "filter" }> | null {
  switch (level.kind) {
    case "entity":
      return null;
    case "component":
      return { kind: "filter", ctype: level.ctype, carrier: null, location: null };
    case "carrier":
      return { kind: "filter", ctype: level.ctype, carrier: level.carrier, location: null };
    case "location":
      return { kind: "filter", ctype: DEFAULT_CTYPE, carrier: null, location: level.location };
    case "bus":
      return { kind: "filter", ctype: DEFAULT_CTYPE, carrier: null, location: level.location };
    case "all-entities":
    case "all-locations":
      return { kind: "filter", ctype: DEFAULT_CTYPE, carrier: null, location: null };
  }
}

/** The target for a level; null while an entity's place is read (or when it isn't in the shown scenario). */
export function useLevelChangeTarget(level: Level | null): DraftChangeTarget | null {
  const entity = level?.kind === "entity" ? level.entity : null;
  const place = useShownData("change-entity-place", entity === null ? null : [entity], () =>
    loadEntityPlace(entity!),
  );
  if (!level) return null;
  if (entity === null) return levelFilterTarget(level);
  if (place.status !== "ready" || !place.data) return null;
  return { kind: "entity", entity, ...place.data };
}
