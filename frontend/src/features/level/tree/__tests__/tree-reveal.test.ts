import { describe, expect, it } from "vitest";
import type { LoadedRecord } from "../../../project/store/types";
import { levelPageId, type Level } from "../../level";
import {
  buildTree,
  busNodeId,
  carrierNodeId,
  ctypeNodeId,
  locationNodeId,
  type TreeNode,
} from "../tree-nodes";
import { revealStep, shownRowOf } from "../tree-reveal";

const record = { carriers: {}, locations: [], zones: [] } as unknown as LoadedRecord;
const counts = [
  { ctype: "Line", carrier: "AC", entities: 2 },
  { ctype: "Generator", carrier: null, entities: 1 },
  { ctype: "Generator", carrier: "solar", entities: 1 },
  { ctype: "Load", carrier: null, entities: 1 },
];
const locations = [{ location: "BE0 0", entities: 3 }];
const tree = (loaded: Record<string, TreeNode[]> = {}) =>
  buildTree(record, counts, locations, loaded);

const lineFolder = carrierNodeId("Line", "AC");
const entity = (parent: string, name: string): TreeNode => ({
  id: `${parent}/${name}`,
  name,
  kind: "entity",
  level: { kind: "entity", entity: name },
});
const line0: Level = { kind: "entity", entity: "Line 0" };
const linePlace = { ctype: "Line", carrier: "AC" };

describe("revealStep", () => {
  it("reveals a type, carrier or location row that exists", () => {
    expect(revealStep({ kind: "component", ctype: "Line" }, tree(), {}, null)).toEqual({
      kind: "reveal",
      id: ctypeNodeId("Line"),
    });
    expect(revealStep({ kind: "carrier", ctype: "Line", carrier: "AC" }, tree(), {}, null)).toEqual(
      { kind: "reveal", id: lineFolder },
    );
    expect(revealStep({ kind: "location", location: "BE0 0" }, tree(), {}, null)).toEqual({
      kind: "reveal",
      id: locationNodeId("BE0 0"),
    });
  });

  it("is done for a row the tree doesn't have, the roots and no level", () => {
    expect(revealStep({ kind: "component", ctype: "Store" }, tree(), {}, null)).toEqual({
      kind: "done",
    });
    expect(revealStep({ kind: "all-entities" }, tree(), {}, null)).toEqual({ kind: "done" });
    expect(revealStep(null, tree(), {}, null)).toEqual({ kind: "done" });
  });

  it("loads a bus's location first, then reveals the bus", () => {
    const bus: Level = { kind: "bus", bus: "B1", location: "BE0 0" };
    const location = locationNodeId("BE0 0");
    expect(revealStep(bus, tree(), {}, null)).toEqual({ kind: "load", id: location });
    const buses = [{ id: busNodeId("B1", "BE0 0"), name: "B1", kind: "bus" as const }];
    const loaded = { [location]: buses };
    expect(revealStep(bus, tree(loaded), loaded, null)).toEqual({
      kind: "reveal",
      id: busNodeId("B1", "BE0 0"),
    });
    // Loaded, and still not there: nothing more to do.
    const none = { [location]: [] };
    expect(revealStep(bus, tree(none), none, null)).toEqual({ kind: "done" });
    expect(revealStep({ kind: "bus", bus: "B1", location: null }, tree(), {}, null)).toEqual({
      kind: "done",
    });
  });

  it("waits for an entity's place, and gives up when it is unknown", () => {
    expect(revealStep(line0, tree(), {}, undefined)).toEqual({ kind: "wait" });
    expect(revealStep(line0, tree(), {}, null)).toEqual({ kind: "done" });
    expect(revealStep(line0, tree(), {}, { ctype: "Store", carrier: null })).toEqual({
      kind: "done",
    });
  });

  it("loads an entity's carrier folder, then reveals its row", () => {
    expect(revealStep(line0, tree(), {}, linePlace)).toEqual({ kind: "load", id: lineFolder });
    const loaded = { [lineFolder]: [entity(lineFolder, "Line 0"), entity(lineFolder, "Line 1")] };
    expect(revealStep(line0, tree(loaded), loaded, linePlace)).toEqual({
      kind: "reveal",
      id: `${lineFolder}/Line 0`,
    });
  });

  it("reveals the folder's 'more' row when its list stops before the entity", () => {
    const more: TreeNode = { id: `${lineFolder}/more`, name: "1 more", kind: "more" };
    const loaded = { [lineFolder]: [entity(lineFolder, "Line 1"), more] };
    expect(revealStep(line0, tree(loaded), loaded, linePlace)).toEqual({
      kind: "reveal",
      id: more.id,
    });
  });

  it("reveals a failed or empty folder's first row", () => {
    const failed: TreeNode = { id: `${lineFolder}/error`, name: "Failed", kind: "placeholder" };
    const loaded = { [lineFolder]: [failed] };
    expect(revealStep(line0, tree(loaded), loaded, linePlace)).toEqual({
      kind: "reveal",
      id: failed.id,
    });
  });

  it("finds a carrier-less entity under its type, or the type's no-carrier row", () => {
    const loadFolder = ctypeNodeId("Load");
    expect(
      revealStep({ kind: "entity", entity: "L" }, tree(), {}, { ctype: "Load", carrier: null }),
    ).toEqual({ kind: "load", id: loadFolder });
    expect(
      revealStep(
        { kind: "entity", entity: "G" },
        tree(),
        {},
        { ctype: "Generator", carrier: null },
      ),
    ).toEqual({ kind: "load", id: carrierNodeId("Generator", null) });
  });

  it("reveals the type when the carrier has no row of its own", () => {
    expect(
      revealStep({ kind: "entity", entity: "G" }, tree(), {}, { ctype: "Generator", carrier: "x" }),
    ).toEqual({ kind: "reveal", id: ctypeNodeId("Generator") });
  });
});

describe("shownRowOf", () => {
  const row = (data: TreeNode) => ({ id: data.id, data });
  const rows = [
    row({ id: "entities", name: "Entities", kind: "category", level: { kind: "all-entities" } }),
    row({ ...entity("bus:B1@BE0 0", "Line 0") }),
    row({ id: "c/more", name: "more", kind: "more", level: { kind: "component", ctype: "Line" } }),
  ];

  it("finds a shown row of the page's level", () => {
    expect(shownRowOf(rows, levelPageId(line0))).toBe("bus:B1@BE0 0/Line 0");
    expect(shownRowOf(rows, null)).toBe("entities");
  });

  it("skips 'more' rows and levels not shown", () => {
    expect(shownRowOf(rows, levelPageId({ kind: "component", ctype: "Line" }))).toBeNull();
    expect(shownRowOf(rows, levelPageId({ kind: "entity", entity: "Line 1" }))).toBeNull();
  });
});
