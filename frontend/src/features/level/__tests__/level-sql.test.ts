import { afterEach, describe, expect, it } from "vitest";
import { setRecordCatalog } from "../../project/lib/record-server/client";
import { entitiesSql, levelCtes, membersSql, scopeKey, spanCondition, spanSql } from "../level-sql";
import { ALL_ENTITIES } from "../level";

afterEach(() => setRecordCatalog(null));

describe("level SQL", () => {
  it("scopes an entity to the investment period by build year and lifetime", () => {
    expect(entitiesSql("2040")).toContain("coalesce(s.build_year, 0) <= 2040 AND 2040 <");
  });

  it("makes every entity active when the period is not a number", () => {
    expect(entitiesSql("base")).toContain("coalesce(NULL::DOUBLE IS NULL");
  });

  it("filters members by level and selected locations, with values quoted", () => {
    const sql = membersSql({ kind: "carrier", ctype: "Generator", carrier: "it's" }, ["BE0 1"]);
    expect(sql).toContain("in_period");
    expect(sql).toContain("ctype = 'Generator'");
    expect(sql).toContain("carrier IS NOT DISTINCT FROM 'it''s'");
    expect(sql).toContain("list_has_any(locations, ['BE0 1'])");
    expect(membersSql(ALL_ENTITIES)).toBe("SELECT * FROM entities WHERE in_period");
  });

  it("limits snapshots to the period and the time window", () => {
    expect(spanCondition("snapshot", "2030", null)).toBe("snapshot.period::VARCHAR = '2030'");
    const window = { start: "2030-01-01T00:00:00Z", end: "2030-01-08T00:00:00Z", label: "Week" };
    const condition = spanCondition("snapshot", "2030", window);
    expect(condition).toContain("snapshot.timestep >= '2030-01-01T00:00:00Z'::TIMESTAMP");
    expect(condition).toContain("snapshot.timestep < '2030-01-08T00:00:00Z'::TIMESTAMP");
  });

  it("keeps only a season's months inside its bounds, and tells windows apart in cache keys", () => {
    const winter = {
      start: "2030-01-01T00:00:00Z",
      end: "2031-01-01T00:00:00Z",
      label: "Winter",
      months: [11, 0, 1],
    };
    expect(spanCondition("snapshot", "2030", winter)).toContain(
      "month(snapshot.timestep) IN (12, 1, 2)",
    );
    const plain = { ...winter, months: undefined };
    const scope = { level: ALL_ENTITIES, period: "2030", timeWindow: winter };
    expect(scopeKey(scope)).not.toBe(scopeKey({ ...scope, timeWindow: plain }));
  });

  it("qualifies every relation with the shown catalog, read when the SQL is built", () => {
    const scope = { level: ALL_ENTITIES, period: "2030", timeWindow: null };
    expect(levelCtes(scope)).not.toContain("rec__base.");
    setRecordCatalog("rec__base");
    const sql = levelCtes(scope);
    expect(sql).toContain("rec__base.properties.entity");
    expect(sql).toContain("rec__base.manta.attribute_summary");
    expect(sql).toContain("rec__base.manta.branches");
    expect(spanSql("2030", null)).toContain("rec__base.dimensions.snapshot");
  });

  it("keys a scope by level, period, window and locations", () => {
    const a = { level: ALL_ENTITIES, period: "2030", timeWindow: null };
    expect(scopeKey(a)).not.toBe(scopeKey({ ...a, period: "2040" }));
    expect(scopeKey(a)).not.toBe(scopeKey({ ...a, locations: ["x"] }));
  });
});
