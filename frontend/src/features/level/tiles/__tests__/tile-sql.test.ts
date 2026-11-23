// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { afterEach, describe, expect, it } from "vitest";
import { setRecordCatalog } from "../../../project/lib/record-server/client";
import { ALL_ENTITIES, ALL_LOCATIONS, type Level } from "../../level";
import { inputParts, inputsSql, resultParts, resultsSql } from "../tile-sql";

afterEach(() => setRecordCatalog(null));

const generators: Level = { kind: "component", ctype: "Generator" };
const window = { start: "2030-01-01T00:00:00Z", end: "2030-01-08T00:00:00Z", label: "Week" };

describe("tile parts by level", () => {
  it("reads volumes and load at the overview levels, and locations at All locations", () => {
    expect(inputParts(ALL_ENTITIES, false)).toMatchObject({
      volumes: true,
      load: true,
      locations: false,
    });
    expect(inputParts(ALL_LOCATIONS, false)).toMatchObject({
      volumes: true,
      load: true,
      locations: true,
    });
  });

  it("reads only a type's own figures", () => {
    expect(inputParts(generators, false)).toMatchObject({
      volumes: false,
      load: false,
      capacityFactor: true,
    });
    expect(inputParts(generators, true).capacityFactor).toBe(false);
    expect(inputParts({ kind: "component", ctype: "Store" }, false)).toMatchObject({
      volumes: true,
      storeEfficiency: true,
    });
    expect(inputParts({ kind: "component", ctype: "Load" }, false).load).toBe(true);
  });

  it("reads the entity itself at an entity level", () => {
    expect(inputParts({ kind: "entity", entity: "g1" }, false).entity).toBe(true);
  });

  it("has result parts only at type, carrier and entity levels", () => {
    expect(resultParts(ALL_ENTITIES)).toBeNull();
    expect(resultParts(generators)).toEqual({ generators: true, stores: false });
    expect(resultParts({ kind: "component", ctype: "Store" })).toEqual({
      generators: false,
      stores: true,
    });
    expect(resultParts({ kind: "entity", entity: "g1" })).toEqual({
      generators: false,
      stores: false,
    });
  });
});

describe("tile SQL", () => {
  const scope = { level: generators, period: "2030", timeWindow: window };

  it("is one query that starts from the level's CTEs", () => {
    const sql = inputsSql(scope, inputParts(generators, false));
    expect(sql.startsWith("WITH entities AS")).toBe(true);
    expect(sql).toContain("members AS");
    expect(sql).toContain("span AS");
    expect(sql.match(/\nSELECT /g)).toHaveLength(1);
  });

  it("weights the window and the period's hours by the snapshot weighting", () => {
    const sql = inputsSql(scope, inputParts(generators, false));
    expect(sql).toContain("snapshot_weighting_generators");
    expect(sql).toContain("span_hours");
    expect(sql).toContain("period_hours");
    expect(sql).toContain("coalesce(w.value, 1)");
  });

  it("limits the capacity factor profile to the time window", () => {
    const sql = inputsSql(scope, inputParts(generators, false));
    expect(sql).toContain("snapshot.timestep >= '2030-01-01T00:00:00Z'::TIMESTAMP");
    expect(sql).toContain("pu_mean");
  });

  it("leaves out parts a level does not show", () => {
    const sql = inputsSql({ ...scope, level: ALL_ENTITIES }, inputParts(ALL_ENTITIES, false));
    expect(sql).toContain("load_points");
    expect(sql).not.toContain("pu_mean");
    expect(sql).not.toContain("location_zones");
    expect(
      inputsSql({ ...scope, level: ALL_LOCATIONS }, inputParts(ALL_LOCATIONS, false)),
    ).toContain("location_zones");
  });

  it("quotes values and honours selected locations", () => {
    const sql = inputsSql(
      {
        level: { kind: "carrier", ctype: "Generator", carrier: "it's" },
        period: "2030",
        timeWindow: null,
        locations: ["BE0 1"],
      },
      inputParts(generators, false),
    );
    expect(sql).toContain("carrier IS NOT DISTINCT FROM 'it''s'");
    expect(sql).toContain("list_has_any(locations, ['BE0 1'])");
  });

  it("builds the result query from the flow at each member's bus", () => {
    const sql = resultsSql(scope, resultParts(generators)!);
    expect(sql).toContain("a.connection.entity");
    expect(sql).toContain("marginal_price");
    expect(sql).not.toContain("attributes.e a");
    expect(
      resultsSql(
        { ...scope, level: { kind: "component", ctype: "Store" } },
        resultParts({ kind: "component", ctype: "Store" })!,
      ),
    ).toContain("attributes.e");
  });

  it("qualifies every relation with the shown catalog, read when the SQL is built (not at import)", () => {
    const parts = inputParts(ALL_LOCATIONS, false);
    const inputs = { ...scope, level: ALL_LOCATIONS };
    expect(inputsSql(inputs, parts)).not.toContain("rec__base.");
    setRecordCatalog("rec__base");
    const sql = inputsSql(inputs, parts);
    expect(sql).toContain("rec__base.manta.attribute_summary");
    expect(sql).toContain("rec__base.manta.location_zones");
    expect(sql).toContain("rec__base.attributes.snapshot_weighting_generators");
    expect(resultsSql(scope, resultParts(generators)!)).toContain("rec__base.attributes.p");
  });
});
