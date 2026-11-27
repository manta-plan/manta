import { afterEach, describe, expect, it } from "vitest";
import { setRecordCatalog } from "../../../project/lib/record-server/client";
import { ALL_ENTITIES } from "../../level";
import { busCarrierOrder } from "../graph/graph-data";
import { shortId } from "../graph/graph-look";
import { boundsOf, locationPoints, padBounds } from "../map/map-geo";
import {
  LINE_COLOURING_OPTIONS,
  REGION_SHADING_ROWS,
  needsResults,
  rampColor,
  regionShadingLabel,
} from "../map/map-layer-store";
import { lineSql, regionSql } from "../map/map-shading";
import {
  baseScope,
  highlightOf,
  isMissingRelation,
  levelOnlyScope,
  lineEndsOf,
  mapSummaryOf,
  routePoints,
  type BranchRow,
  type BusRow,
  type Highlight,
} from "../map-graph-data";
import { mapSummaryText } from "../map/map-summary";

afterEach(() => setRecordCatalog(null));

const bus = (name: string, location: string, x: number, y: number, carrier = "AC"): BusRow => ({
  bus: name,
  carrier,
  location,
  x,
  y,
});

const buses = [
  bus("BE0 1 H2", "BE0 1", 4.4, 50.8, "H2"),
  bus("BE0 1", "BE0 1", 4.5, 50.9),
  bus("BE0 2", "BE0 2", 5.1, 50.6),
  bus("BE0 3", "BE0 3", Number.NaN, 50.6),
];

describe("map geometry", () => {
  it("places a location at the bus named after it, else its first with coordinates", () => {
    const points = locationPoints(buses);
    expect(points.get("BE0 1")).toEqual([4.5, 50.9]);
    expect(points.get("BE0 2")).toEqual([5.1, 50.6]);
    expect(points.has("BE0 3")).toBe(false);
  });

  it("bounds points, and none for no points", () => {
    expect(
      boundsOf([
        [1, 5],
        [3, 2],
      ]),
    ).toEqual([
      [1, 2],
      [3, 5],
    ]);
    expect(boundsOf([])).toBeNull();
  });

  it("pads bounds by a share of the larger side, at least min degrees across", () => {
    const [[w, s], [e, n]] = padBounds(
      [
        [0, 0],
        [2, 1],
      ],
      0.5,
    );
    expect([w, s, e, n]).toEqual([-1, -1, 3, 2]);
    const [[w2], [e2]] = padBounds(
      [
        [1, 1],
        [1, 1],
      ],
      0,
      0.08,
    );
    expect(e2 - w2).toBeCloseTo(0.08);
  });

  it("joins the parts of a multilinestring into one route", () => {
    expect(routePoints("LINESTRING(0 0, 1 1)")).toEqual([
      [0, 0],
      [1, 1],
    ]);
    expect(routePoints("MULTILINESTRING((0 0, 1 1), (2 2, 3 3))")).toHaveLength(4);
    expect(routePoints("POINT(1 1)")).toEqual([]);
  });
});

describe("graph helpers", () => {
  it("orders bus carriers by own-named buses first, then by count", () => {
    expect(busCarrierOrder(buses)).toEqual(["AC", "H2"]);
    expect(busCarrierOrder([])).toEqual([]);
  });

  it("cuts long ids with an ellipsis", () => {
    expect(shortId("abcdef", 6)).toBe("abcdef");
    expect(shortId("abcdefg", 6)).toBe("abcde…");
  });
});

describe("what the level highlights", () => {
  const branches: BranchRow[] = [
    {
      entity: "L1",
      ctype: "Line",
      carrier: "AC",
      bus0: "BE0 1",
      bus1: "BE0 2",
      location0: "BE0 1",
      location1: "BE0 2",
      capacity: 100,
      capacity_opt: null,
    },
  ];
  const row = { locations: ["BE0 1"], buses: ["BE0 1"], lines: [], members: 3 };

  it("lights everything at the all levels", () => {
    const h = highlightOf(ALL_ENTITIES, row, buses, branches);
    expect(h.all).toBe(true);
    expect(h.lines.has("L1")).toBe(true);
    expect(h.locations.has("BE0 2")).toBe(true);
  });

  it("lights a location's own buses, and a bus's location", () => {
    const loc = highlightOf({ kind: "location", location: "BE0 1" }, row, buses, branches);
    expect([...loc.buses].sort()).toEqual(["BE0 1", "BE0 1 H2"]);
    const one = highlightOf({ kind: "bus", bus: "BE0 2", location: null }, row, buses, branches);
    expect([...one.locations]).toEqual(["BE0 2"]);
  });

  it("lights both ends of a Line entity", () => {
    const h = highlightOf({ kind: "entity", entity: "L1" }, row, buses, branches);
    expect([...h.locations].sort()).toEqual(["BE0 1", "BE0 2"]);
    expect(h.buses.has("BE0 2")).toBe(true);
  });

  it("drops the level's filters for what the whole map reads", () => {
    const scope = {
      level: { kind: "location" as const, location: "BE0 1" },
      period: "2030",
      timeWindow: null,
      locations: ["BE0 1"],
      filter: { kind: "component" as const, ctype: "Generator" },
    };
    expect(baseScope(scope)).toEqual({
      level: ALL_ENTITIES,
      period: "2030",
      timeWindow: null,
      locations: [],
      filter: null,
    });
    expect(levelOnlyScope(scope).locations).toEqual([]);
    expect(levelOnlyScope(scope).level).toBe(scope.level);
    // The highlight keeps the cross-tree filter: Generators at a location light only theirs.
    expect(levelOnlyScope(scope).filter).toBe(scope.filter);
  });
});

describe("layer shading", () => {
  it("has a query for every region shading and line colouring, in the shown catalog", () => {
    setRecordCatalog("rec");
    for (const { options } of REGION_SHADING_ROWS) {
      for (const option of options) {
        for (const withResults of [false, true]) {
          const { sql } = regionSql(option.id, withResults);
          expect(sql.length).toBeGreaterThan(0);
          // Every relation is qualified; none is bare.
          expect(sql).not.toMatch(/FROM (attributes|properties|manta)\./);
        }
      }
    }
    for (const option of LINE_COLOURING_OPTIONS)
      expect(lineSql(option.id, true).sql).toContain("e.entity AS key");
  });

  it("reads the optimised capacity only with results", () => {
    setRecordCatalog("rec");
    expect(regionSql("generator-capacity", false).sql).not.toContain("capacity_opt");
    expect(regionSql("generator-capacity", true).sql).toContain(
      "coalesce(e.capacity_opt, e.capacity)",
    );
    expect(regionSql("generator-capacity", true).unit).toBe("MW, optimised");
    expect(lineSql("capacity", false).unit).toBe("MVA");
  });

  it("reads storage volume from max_hours through the attribute summary", () => {
    setRecordCatalog("rec");
    expect(regionSql("storage-volume", false).sql).toContain("rec.manta.attribute_summary");
  });

  it("marks the shadings that need run results", () => {
    expect(needsResults("generator-utilisation")).toBe(true);
    expect(needsResults("generator-capacity")).toBe(false);
    expect(needsResults("loading")).toBe(true);
    expect(regionShadingLabel("bus-price")).toBe("Bus · Mean price");
  });

  it("runs the colour ramp from blue to orange", () => {
    expect(rampColor(0)).toBe("hsl(210, 70%, 55%)");
    expect(rampColor(1)).toBe("hsl(20, 70%, 55%)");
    expect(rampColor(5)).toBe(rampColor(1));
  });
});

describe("isMissingRelation", () => {
  it("is true only for a missing manta.entity_geometry", () => {
    expect(
      isMissingRelation(
        new Error("Catalog Error: Table with name entity_geometry does not exist!"),
      ),
    ).toBe(true);
    expect(isMissingRelation(new Error("Query timed out"))).toBe(false);
    expect(isMissingRelation(new Error("Table with name bus does not exist"))).toBe(false);
  });
});

describe("map summary", () => {
  const branch = (
    entity: string,
    location0: string,
    location1: string,
    ctype = "Line",
  ): BranchRow => ({
    entity,
    ctype,
    carrier: "AC",
    bus0: location0,
    bus1: location1,
    location0,
    location1,
    capacity: null,
    capacity_opt: null,
  });
  const branches = [
    branch("L1", "BE0 1", "BE0 2"),
    branch("L2", "BE0 2", "BE0 3"),
    branch("K1", "BE0 1", "BE0 3", "Link"),
  ];
  const highlight = (lines: string[], locations: string[], members = 4): Highlight => ({
    all: false,
    locations: new Set(locations),
    buses: new Set(locations),
    lines: new Set(lines),
    members,
  });

  it("counts far line ends the level doesn't highlight", () => {
    expect([...lineEndsOf(highlight(["L1", "L2"], ["BE0 2"]), branches)].sort()).toEqual([
      "BE0 1",
      "BE0 3",
    ]);
    expect(lineEndsOf({ ...highlight(["L1"], []), all: true }, branches).size).toBe(0);
    // Links aren't lines.
    expect(lineEndsOf(highlight(["K1"], []), branches).size).toBe(0);
  });

  it("summarises buses, lines and sited entities", () => {
    const summary = mapSummaryOf(
      { kind: "location", location: "BE0 2" },
      highlight(["L1"], ["BE0 2"], 202),
      buses,
      branches,
      [],
    );
    expect(summary).toEqual({
      buses: 1,
      allBuses: 4,
      lineEnds: 1,
      lines: 1,
      allLines: 2,
      located: 0,
      members: 202,
    });
    expect(mapSummaryText(summary, true)).toBe(
      "1 of 4 buses, 1 line ends · 1 of 2 lines · 0 of 202 entities have their own location",
    );
  });

  it("counts every line for All entities, one member for an entity, no siting without geometry", () => {
    const all = mapSummaryOf(
      { kind: "all-entities" },
      { ...highlight([], []), all: true },
      buses,
      branches,
      null,
    );
    expect(all).toMatchObject({ lines: 2, allLines: 2, located: null });
    expect(mapSummaryText(all, true)).toBe("0 of 4 buses · 2 of 2 lines");
    const one = mapSummaryOf({ kind: "entity", entity: "L1" }, highlight([], []), buses, null, [
      { entity: "L1", ctype: "Line", carrier: null, location: null, lon: 0, lat: 0 },
    ]);
    expect(one).toMatchObject({ members: 1, located: 1, allLines: 0 });
    expect(mapSummaryText(one, false)).toContain(
      "1 of 1 entities have their own location; siting hidden",
    );
    expect(mapSummaryText(one, true)).toContain("; dashed lines join them to their bus");
  });
});
