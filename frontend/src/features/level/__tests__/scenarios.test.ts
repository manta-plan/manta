import { afterEach, describe, expect, it } from "vitest";
import {
  applyChanges,
  draftScenarioOptions,
  isChangeable,
  targetMatches,
  toChangeSet,
  type DraftScenario,
} from "../../project/lib/draft-scenarios";
import { setRecordCatalog } from "../../project/lib/record-server/client";
import type { Revision } from "../../project/lib/record-server/types";
import { loadDraftFigures, loadMatches } from "../scenarios/change-sql";
import { filterWords, opWords, plural } from "../scenarios/change-wording";
import { levelFilterTarget } from "../scenarios/level-target";

afterEach(() => setRecordCatalog(null));

const draft: DraftScenario = {
  id: "d1",
  recordId: "rec",
  parent: "base",
  name: "Solar +30%",
  description: "why",
  createdAt: "",
  updatedAt: "",
  changes: [
    {
      id: "c1",
      kind: "attribute",
      attribute: "capital_cost",
      target: { kind: "filter", ctype: "Generator", carrier: "solar", location: null },
      op: "multiply",
      value: 1.3,
    },
    {
      id: "c2",
      kind: "attribute",
      attribute: "p_nom",
      target: {
        kind: "entity",
        entity: "g1",
        ctype: "Generator",
        carrier: null,
        location: "BE0 1",
      },
      op: "set",
      value: 5,
    },
    {
      id: "c3",
      kind: "new-entity",
      entity: "new gen",
      ctype: "Generator",
      carrier: "wind",
      buses: { attached: "b1" },
      values: { p_nom: 2 },
    },
  ],
};

describe("toChangeSet", () => {
  it("hands the backend the parent and each change in order", () => {
    const set = toChangeSet(draft);
    expect(set).toMatchObject({ version: 1, record: "rec", parent: "base", name: "Solar +30%" });
    expect(set.changes).toEqual([
      {
        attribute: "capital_cost",
        where: { ctype: "Generator", carrier: "solar" },
        op: "multiply",
        value: 1.3,
      },
      { attribute: "p_nom", where: { entity: "g1" }, op: "set", value: 5 },
      {
        op: "create",
        entity: "new gen",
        properties: { ctype: "Generator", carrier: "wind" },
        connections: [{ role: "attached", bus: "b1" }],
        values: { p_nom: 2 },
      },
    ]);
  });
});

describe("draft logic", () => {
  it("applies changes in order and gives up without a base for multiply or add", () => {
    expect(
      applyChanges(10, [
        { op: "multiply", value: 2 },
        { op: "add", value: -4 },
      ]),
    ).toBe(16);
    expect(applyChanges(null, [{ op: "multiply", value: 2 }])).toBeNull();
    expect(
      applyChanges(null, [
        { op: "set", value: 3 },
        { op: "add", value: 1 },
      ]),
    ).toBe(4);
  });

  it("matches a filter on type, carrier and location, and an entity by name", () => {
    const subject = { entity: "g1", ctype: "Generator", carrier: "solar", locations: ["A"] };
    expect(
      targetMatches({ kind: "filter", ctype: "Generator", carrier: null, location: "A" }, subject),
    ).toBe(true);
    expect(
      targetMatches(
        { kind: "filter", ctype: "Generator", carrier: "wind", location: null },
        subject,
      ),
    ).toBe(false);
    expect(
      targetMatches(
        { kind: "entity", entity: "g1", ctype: "x", carrier: null, location: null },
        subject,
      ),
    ).toBe(true);
  });

  it("offers only changeable attributes", () => {
    expect(isChangeable({ dims: ["entity"], dtype: "float64" })).toBe(true);
    expect(isChangeable({ dims: ["entity", "connection"] })).toBe(false);
    expect(isChangeable({ dims: ["entity"], one_of: "a" })).toBe(false);
    expect(isChangeable({ dims: ["entity"], dtype: "string" })).toBe(false);
    expect(isChangeable(undefined)).toBe(false);
  });

  it("enables only options built on the shown scenario", () => {
    const rev = (name: string, parent: string | null): Revision =>
      ({ name, label: name, kind: "scenario", parent }) as Revision;
    const field = draftScenarioOptions([draft, { ...draft, id: "d2", parent: "other" }], {
      recordId: "rec",
      revisions: [rev("base", null), rev("other", "base")],
      shown: "base",
      newValue: "__new__",
    });
    expect(field.usable.map((item) => item.id)).toEqual(["d1"]);
    expect(field.options.find((o) => o.value === "__new__")?.disabled).toBeUndefined();
    expect(field.options.find((o) => o.value === "__new__:other")?.disabled).toBe(true);
    expect(field.options.find((o) => o.value === "saved:other")?.disabled).toBe(true);
    expect(field.hint).toBeDefined();
  });
});

describe("change wording", () => {
  it("words operations, filters and counts", () => {
    expect(opWords("multiply", 1.3)).toBe("multiply by 1.3");
    expect(opWords("add", -2, "MW")).toBe("add -2 MW");
    expect(opWords("set", 5, "MW")).toBe("set to 5 MW");
    expect(
      filterWords(
        { kind: "filter", ctype: "Generator", carrier: "solar", location: "BE0 1" },
        (c) => c.toUpperCase(),
      ),
    ).toBe("Generator SOLAR at BE0 1");
    expect(plural(1, "entity", "entities")).toBe("1 entity");
    expect(plural(1200, "entity", "entities")).toContain("entities");
  });

  it("defaults group levels without a type to Generator", () => {
    expect(levelFilterTarget({ kind: "all-entities" })).toMatchObject({ ctype: "Generator" });
    expect(levelFilterTarget({ kind: "carrier", ctype: "Load", carrier: "x" })).toMatchObject({
      ctype: "Load",
      carrier: "x",
    });
    expect(levelFilterTarget({ kind: "entity", entity: "e" })).toBeNull();
  });
});

describe("change SQL", () => {
  it("builds queries lazily through serverName, quoted and scoped to the period", async () => {
    // Without a connection the query rejects, but the SQL is built first; capture it.
    setRecordCatalog("rec__base");
    const sqls: string[] = [];
    const client = await import("../../project/lib/record-server/client");
    const { vi } = await import("vitest");
    const spy = vi.spyOn(client, "serverQuery").mockImplementation(async (sql: string) => {
      sqls.push(sql);
      return [];
    });
    await loadMatches(
      { kind: "filter", ctype: "Generator", carrier: "it's", location: "A" },
      "2030",
    );
    await loadDraftFigures(draft.changes, "2030");
    spy.mockRestore();
    const [matches, counts, stored] = sqls;
    expect(matches).toContain("e.in_period AND e.ctype = 'Generator'");
    expect(matches).toContain("e.carrier = 'it''s'");
    expect(matches).toContain("list_contains(e.locations, 'A')");
    expect(matches).toContain("rec__base");
    expect(counts).toContain("VALUES ('c1', 'Generator', 'solar', NULL::VARCHAR)");
    expect(stored).toContain("('g1', 'p_nom')");
    expect(stored).toContain("s.bus IS NULL");
  });
});
