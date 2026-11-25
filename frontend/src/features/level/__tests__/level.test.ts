// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import {
  ALL_ENTITIES,
  ALL_LOCATIONS,
  isLocationLevel,
  levelFilter,
  levelOfPageId,
  levelPageId,
  type Level,
} from "../level";

describe("level page ids", () => {
  const levels: [Level, string | null][] = [
    [ALL_ENTITIES, null],
    [{ kind: "component", ctype: "Generator" }, "component:Generator"],
    [{ kind: "carrier", ctype: "Generator", carrier: "solar" }, "component:Generator:solar"],
    [{ kind: "entity", entity: "BE0 1 solar/2030" }, "entity:BE0%201%20solar%2F2030"],
    [ALL_LOCATIONS, "locations"],
    [{ kind: "location", location: "BE0 1" }, "location:BE0%201"],
    [{ kind: "bus", bus: "BE0 1 H2", location: "BE0 1" }, "bus:BE0%201%20H2@BE0%201"],
    [{ kind: "bus", bus: "BE0 1 H2", location: null }, "bus:BE0%201%20H2"],
  ];

  it.each(levels)("round trips %j", (level, id) => {
    expect(levelPageId(level)).toBe(id);
    expect(levelOfPageId(id)).toEqual(level);
  });

  it("reads no id as All entities and an unknown id as no level", () => {
    expect(levelOfPageId(undefined)).toEqual(ALL_ENTITIES);
    expect(levelOfPageId("compare:a:b")).toBeNull();
    expect(levelOfPageId("nonsense")).toBeNull();
  });

  it("tells location levels from entity levels", () => {
    expect(isLocationLevel(ALL_LOCATIONS)).toBe(true);
    expect(isLocationLevel({ kind: "bus", bus: "b", location: null })).toBe(true);
    expect(isLocationLevel(ALL_ENTITIES)).toBe(false);
  });

  it("filters members by what the level names", () => {
    expect(levelFilter({ kind: "carrier", ctype: "Generator", carrier: "solar" })).toEqual({
      ctype: "Generator",
      carrier: "solar",
      location: null,
      bus: null,
      entity: null,
    });
  });
});
