import { afterEach, describe, expect, it } from "vitest";
import { setRecordCatalog } from "../../project/lib/record-server/client";
import { levelBusesSql } from "../chart/chart-sql";
import { ALL_ENTITIES, ALL_LOCATIONS, type Level } from "../level";
import { crossFilterLabel, pickLevel, treeOf } from "../level-pick";
import { membersSql, scopeKey, type LevelQueryScope } from "../level-sql";
import { useLevelStore } from "../level-store";

afterEach(() => {
  setRecordCatalog(null);
  useLevelStore.getState().resetForProject();
});

const generator: Level = { kind: "component", ctype: "Generator" };
const solar: Level = { kind: "carrier", ctype: "Generator", carrier: "solar" };
const location: Level = { kind: "location", location: "BE0 0" };
const bus: Level = { kind: "bus", bus: "BE0 0 AC", location: "BE0 0" };
const entity: Level = { kind: "entity", entity: "Line 0" };

describe("treeOf", () => {
  it("puts group levels in their tree, and roots and entities in none", () => {
    expect([generator, solar, location, bus].map(treeOf)).toEqual([
      "entities",
      "entities",
      "locations",
      "locations",
    ]);
    expect([ALL_ENTITIES, ALL_LOCATIONS, entity].map(treeOf)).toEqual([null, null, null]);
  });
});

describe("pickLevel", () => {
  it("narrows a location by a component or carrier picked after it", () => {
    expect(pickLevel(location, generator)).toEqual({ kind: "filter", filter: generator });
    expect(pickLevel(bus, solar)).toEqual({ kind: "filter", filter: solar });
  });

  it("narrows a component by a location or bus picked after it, the other way round", () => {
    expect(pickLevel(generator, location)).toEqual({ kind: "filter", filter: location });
    expect(pickLevel(solar, bus)).toEqual({ kind: "filter", filter: bus });
  });

  it("opens a pick from the context's own tree", () => {
    expect(pickLevel(location, { kind: "location", location: "BE1 0" })).toEqual({
      kind: "open",
      level: { kind: "location", location: "BE1 0" },
    });
    expect(pickLevel(location, bus)).toEqual({ kind: "open", level: bus });
    expect(pickLevel(generator, solar)).toEqual({ kind: "open", level: solar });
  });

  it("opens entities and roots, and anything picked on a root or an entity's page", () => {
    expect(pickLevel(location, entity)).toEqual({ kind: "open", level: entity });
    expect(pickLevel(generator, ALL_LOCATIONS)).toEqual({ kind: "open", level: ALL_LOCATIONS });
    expect(pickLevel(ALL_ENTITIES, location)).toEqual({ kind: "open", level: location });
    expect(pickLevel(ALL_LOCATIONS, generator)).toEqual({ kind: "open", level: generator });
    expect(pickLevel(entity, generator)).toEqual({ kind: "open", level: generator });
  });
});

describe("crossFilterLabel", () => {
  it("names the filter, with the carrier's nice name", () => {
    expect(crossFilterLabel({ kind: "component", ctype: "Generator" })).toBe("Generator");
    expect(
      crossFilterLabel({ kind: "carrier", ctype: "Generator", carrier: "solar" }, () => "Solar"),
    ).toBe("Generator · Solar");
    expect(crossFilterLabel({ kind: "location", location: "BE0 0" })).toBe("BE0 0");
    expect(crossFilterLabel({ kind: "bus", bus: "B", location: null })).toBe("Bus B");
  });
});

describe("cross-tree filter in SQL", () => {
  it("adds the filter's conditions to the level's", () => {
    const sql = membersSql(location, [], { kind: "carrier", ctype: "Generator", carrier: "solar" });
    expect(sql).toBe(
      "SELECT * FROM entities WHERE in_period AND list_contains(locations, 'BE0 0') AND ctype = 'Generator' AND carrier IS NOT DISTINCT FROM 'solar'",
    );
    expect(membersSql(generator, [], { kind: "bus", bus: "B", location: "L" })).toBe(
      "SELECT * FROM entities WHERE in_period AND ctype = 'Generator' AND list_contains(buses, 'B')",
    );
  });

  it("keys a filtered scope apart from the plain one", () => {
    const plain: LevelQueryScope = { level: location, period: "2030", timeWindow: null };
    expect(scopeKey({ ...plain, filter: { kind: "component", ctype: "Generator" } })).not.toBe(
      scopeKey(plain),
    );
    expect(scopeKey({ ...plain, filter: null })).toBe(scopeKey(plain));
  });

  it("reads the buses of a location or bus filter for a component's prices", () => {
    const scope: LevelQueryScope = {
      level: generator,
      period: "2030",
      timeWindow: null,
      filter: { kind: "location", location: "BE0 0" },
    };
    expect(levelBusesSql(scope, true)).toContain("b.location = 'BE0 0'");
    expect(
      levelBusesSql({ ...scope, filter: { kind: "bus", bus: "B", location: null } }, false),
    ).toBe("SELECT 'B' AS bus");
    expect(levelBusesSql({ ...scope, filter: null }, true)).not.toContain("b.location =");
  });
});

describe("crossFilter in the store", () => {
  it("is kept for its page and cleared on opening another level", () => {
    const store = useLevelStore.getState();
    store.setCrossFilter("location:BE0%200", { kind: "component", ctype: "Generator" });
    expect(useLevelStore.getState().crossFilter).toEqual({
      context: "location:BE0%200",
      filter: { kind: "component", ctype: "Generator" },
    });
    store.setCrossFilter("location:BE0%200", null);
    expect(useLevelStore.getState().crossFilter).toBeNull();
    store.setCrossFilter("location:BE0%200", { kind: "component", ctype: "Load" });
    useLevelStore.getState().resetForLevel();
    expect(useLevelStore.getState().crossFilter).toBeNull();
  });
});
