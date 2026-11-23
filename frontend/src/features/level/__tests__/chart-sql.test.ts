import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const queries: string[] = [];
vi.mock("../../project/lib/record-server/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../project/lib/record-server/client")>()),
  serverQuery: vi.fn(async (sql: string) => {
    queries.push(sql);
    return [];
  }),
}));

import { setRecordCatalog } from "../../project/lib/record-server/client";
import { ALL_ENTITIES } from "../level";
import type { LevelQueryScope } from "../level-sql";
import {
  attributeDim,
  loadAttributeAggregate,
  loadAttributeEach,
  loadAttributeOptions,
  loadAvailable,
  loadAxis,
  loadOptimisedMix,
  loadPicked,
} from "../chart/chart-sql";

const scope: LevelQueryScope = { level: ALL_ENTITIES, period: "2030", timeWindow: null };

beforeEach(() => {
  queries.length = 0;
});
afterEach(() => setRecordCatalog(null));

describe("chart SQL", () => {
  it("picks where an attribute sits from the manifest's dims", () => {
    expect(attributeDim(["entity", "connection"])).toBe("connection");
    expect(attributeDim(["bus"])).toBe("bus");
    expect(attributeDim(["bus", "entity"])).toBe("entity");
    expect(attributeDim(undefined)).toBe("entity");
  });

  it("reads the axis from the period's snapshots in the shown catalog", async () => {
    setRecordCatalog("rec");
    await loadAxis(scope);
    expect(queries[0]).toContain("rec.dims.snapshot");
    expect(queries[0]).toContain("rec.attributes.snapshot_weighting_generators");
    expect(queries[0]).toContain("snapshot.period::VARCHAR = '2030'");
  });

  it("qualifies every relation with the catalog, resolved per call (not at import)", async () => {
    // The catalog is set only now, after the module loaded: a name built at import would be bare.
    setRecordCatalog("rec");
    await loadAvailable(scope, { optimised: false, vreOnly: true, byCarrier: true });
    expect(queries[0]).toContain("rec.manta.attribute_summary");
    expect(queries[0]).toContain('rec.attributes."p_max_pu"');
    setRecordCatalog("other");
    await loadAvailable(scope, { optimised: false, vreOnly: true, byCarrier: true });
    expect(queries[1]).toContain("other.manta.attribute_summary");
    expect(queries[1]).not.toContain("rec.");
  });

  it("starts every read from the level's CTEs and joins the span", async () => {
    setRecordCatalog("rec");
    await loadAttributeAggregate(
      scope,
      { ctype: "Generator", attribute: "p_max_pu", dim: "entity", optimised: false },
      "weighted",
    );
    const sql = queries[0];
    expect(sql).toMatch(/WITH entities AS/);
    expect(sql).toContain("span AS");
    expect(sql).toContain("FROM span t CROSS JOIN keys k");
    expect(sql).toContain("capacity AS weight");
  });

  it("weights by optimised capacity in a run result", async () => {
    await loadAttributeAggregate(
      scope,
      { ctype: "Generator", attribute: "p_max_pu", dim: "entity", optimised: true },
      "mean",
    );
    expect(queries[0]).toContain("coalesce(capacity_opt, capacity) AS weight");
    expect(queries[0]).toContain("avg(v.value)");
  });

  it("orders the options by columns, and keeps ORDER BY on selected columns with GROUP BY ALL", async () => {
    await loadAttributeOptions(scope, true);
    const sql = queries.find((q) => q.includes("GROUP BY ALL"))!;
    expect(sql).toContain("ORDER BY 1, 2");
    expect(queries.some((q) => q.includes("manta.bus_location"))).toBe(true);
  });

  it("returns nothing for Each when no series is found, without a second read", async () => {
    expect(
      await loadAttributeEach(
        scope,
        { ctype: "Load", attribute: "p_set", dim: "entity", optimised: false },
        12,
      ),
    ).toEqual([]);
    expect(queries).toHaveLength(1);
    expect(queries[0]).toContain("LIMIT 12");
  });

  it("makes a connection attribute's join pick the entity's own end", async () => {
    await loadPicked(scope, [{ attribute: "p", dim: "connection", subject: "G 1", bus: null }]);
    expect(queries[0]).toContain("role IN ('attached', 'input')");
    expect(queries[0]).toContain("'G 1'");
  });

  it("quotes names into the optimised mix query", async () => {
    await loadOptimisedMix(
      { ...scope, level: { kind: "bus", bus: "it's", location: null } },
      "capacity",
      "bus",
    );
    expect(queries[0]).toContain("'it''s'");
  });
});
