// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { describe, expect, it, vi } from "vitest";
import type { LoadedRecord } from "../../../project/store/types";

vi.mock("../tree-queries", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../tree-queries")>()),
  treeBuses: vi.fn(async () => [
    { bus: "BE0 0", carrier: "AC", entities: 3 },
    { bus: "BE0 0 H2", carrier: null, entities: 0 },
  ]),
  treeLeaves: vi.fn(async () => [
    { entity: "g1", ctype: "Generator", carrier: "solar", location: "BE0 0", total: 5 },
    { entity: "g2", ctype: "Generator", carrier: "solar", location: "BE0 0", total: 5 },
  ]),
}));

import {
  ENTITIES_ID,
  LOCATIONS_ID,
  buildTree,
  busNodeId,
  carrierNodeId,
  ctypeNodeId,
  loadChildren,
  locationNodeId,
  regionsOf,
  type TreeNode,
} from "../tree-nodes";
import { contains } from "../tree-queries";
import { activateTreeRow } from "../tree-actions";
import type { NodeApi } from "react-arborist";

const record = {
  carriers: { solar: { niceName: "Solar", color: "#fc0" } },
  locations: [{ location: "BE0 0" }, { location: "BE1 0" }, { location: "BE2 0" }],
  zones: [
    { level: "busmap_all", location: "BE0 0", zone: "BE0 0" },
    { level: "busmap_all", location: "BE1 0", zone: "BE1 0" },
    { level: "busmap_all", location: "BE2 0", zone: "BE2 0" },
    { level: "busmap_2", location: "BE0 0", zone: "N" },
    { level: "busmap_2", location: "BE1 0", zone: "N" },
    { level: "busmap_2", location: "BE2 0", zone: "S" },
  ],
} as unknown as LoadedRecord;

const counts = [
  { ctype: "Generator", carrier: "solar", entities: 5 },
  { ctype: "Generator", carrier: "wind", entities: 9 },
  { ctype: "Load", carrier: null, entities: 3 },
  { ctype: "Bus", carrier: "AC", entities: 20 },
];
const locations = [
  { location: "BE2 0", entities: 1 },
  { location: "BE0 0", entities: 4 },
  { location: "BE1 0", entities: 2 },
];

describe("buildTree", () => {
  const [entities, locs] = buildTree(record, counts, locations, {});

  it("has the two roots with totals", () => {
    expect(entities).toMatchObject({
      id: ENTITIES_ID,
      detail: "37",
      level: { kind: "all-entities" },
    });
    expect(locs).toMatchObject({ id: LOCATIONS_ID, detail: "3", level: { kind: "all-locations" } });
  });

  it("orders types by entity count and carriers within a type", () => {
    expect(entities.children?.map((node) => node.name)).toEqual(["Bus", "Generator", "Load"]);
    const generator = entities.children![1];
    expect(generator.children?.map((node) => node.id)).toEqual([
      carrierNodeId("Generator", "wind"),
      carrierNodeId("Generator", "solar"),
    ]);
    // known carriers use their nice name and colour; unknown ones their id
    expect(generator.children?.[1]).toMatchObject({ name: "Solar", color: "#fc0", title: "solar" });
    expect(generator.children?.[0].name).toBe("wind");
  });

  it("makes a type without carriers lazy, opening its own level", () => {
    const load = entities.children![2];
    expect(load.id).toBe(ctypeNodeId("Load"));
    expect(load.children?.every((node) => node.kind === "placeholder")).toBe(true);
    expect(load.lazy).toMatchObject({ kind: "leaves", filter: { kind: "type", ctype: "Load" } });
  });

  it("gives a no-carrier row (among carriers) its type's level", () => {
    const [mixed] = buildTree(
      record,
      [
        { ctype: "X", carrier: null, entities: 1 },
        { ctype: "X", carrier: "solar", entities: 2 },
      ],
      [],
      {},
    ).slice(0, 1);
    const none = mixed.children![0].children!.find((node) => node.name === "(no carrier)");
    expect(none?.level).toEqual({ kind: "component", ctype: "X" });
  });

  it("sorts locations by region then name, with the region as a pill", () => {
    expect(locs.children?.map((node) => [node.name, node.pill])).toEqual([
      ["BE0 0", "N"],
      ["BE1 0", "N"],
      ["BE2 0", "S"],
    ]);
    expect(locs.children?.[0].level).toEqual({ kind: "location", location: "BE0 0" });
  });

  it("shows skeleton rows for unloaded lazy nodes and loaded children after", () => {
    const loc = locs.children![0];
    expect(loc.children?.map((node) => node.kind)).toEqual([
      "placeholder",
      "placeholder",
      "placeholder",
    ]);
    const loaded: TreeNode[] = [{ id: "x", name: "x", kind: "bus" }];
    const [, withLoaded] = buildTree(record, counts, locations, { [loc.id]: loaded });
    expect(withLoaded.children![0].children).toEqual(loaded);
  });
});

describe("regionsOf", () => {
  it("uses the zone level with the fewest zones above one", () => {
    expect(regionsOf(record).get("BE2 0")).toBe("S");
  });
  it("is empty without a grouping zone level", () => {
    expect(regionsOf({ ...record, zones: [] } as unknown as LoadedRecord).size).toBe(0);
  });
});

describe("loadChildren", () => {
  it("lists a location's buses as levels", async () => {
    const nodes = await loadChildren(
      { kind: "buses", location: "BE0 0" },
      "location:BE0 0",
      record,
      "2030",
    );
    expect(nodes[0]).toMatchObject({
      id: busNodeId("BE0 0", "BE0 0"),
      kind: "bus",
      detail: "3",
      level: { kind: "bus", bus: "BE0 0", location: "BE0 0" },
    });
  });

  it("lists entities per parent with a 'more' row for the rest", async () => {
    const level = { kind: "carrier", ctype: "Generator", carrier: "solar" } as const;
    const nodes = await loadChildren(
      { kind: "leaves", filter: { kind: "type", ctype: "Generator", carrier: "solar" }, level },
      "carrier:Generator:solar",
      record,
      "2030",
    );
    expect(nodes.map((node) => node.id)).toEqual([
      "carrier:Generator:solar/g1",
      "carrier:Generator:solar/g2",
      "carrier:Generator:solar/more",
    ]);
    expect(nodes[0].level).toEqual({ kind: "entity", entity: "g1" });
    expect(nodes[2]).toMatchObject({ kind: "more", name: "3 more in the table", level });
  });

  it("shows the type under a bus", async () => {
    const nodes = await loadChildren(
      {
        kind: "leaves",
        filter: { kind: "bus", bus: "b" },
        level: { kind: "bus", bus: "b", location: "l" },
      },
      locationNodeId("l"),
      record,
      "2030",
    );
    expect(nodes[0].detail).toBe("Generator");
  });
});

describe("contains", () => {
  it("ANDs the words, escaping wildcards", () => {
    expect(contains("entity", "wind  50%")).toBe(
      "entity ILIKE '%wind%' ESCAPE '\\' AND entity ILIKE '%50\\%%' ESCAPE '\\'",
    );
  });
  it("matches nothing for an empty term", () => {
    expect(contains("entity", "  ")).toBe("false");
  });
});

describe("activateTreeRow", () => {
  const node = (isInternal: boolean, isOpen: boolean) =>
    ({ isInternal, isOpen, open: vi.fn(), toggle: vi.fn() }) as unknown as NodeApi<unknown> & {
      open: ReturnType<typeof vi.fn>;
      toggle: ReturnType<typeof vi.fn>;
    };
  it("opens the level and unfolds, never folds", () => {
    const n = node(true, false);
    const open = vi.fn();
    activateTreeRow(n, open);
    expect(open).toHaveBeenCalled();
    expect(n.open).toHaveBeenCalled();
    const o = node(true, true);
    activateTreeRow(o, open);
    expect(o.open).not.toHaveBeenCalled();
    expect(o.toggle).not.toHaveBeenCalled();
  });
  it("toggles a folder with nothing to open", () => {
    const n = node(true, true);
    activateTreeRow(n, null);
    expect(n.toggle).toHaveBeenCalled();
  });
});
