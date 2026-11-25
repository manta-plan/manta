// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import type { Level } from "../level";
import { statisticsFor } from "../chart/statistics";
import {
  aggregationsFor,
  attributeOptions,
  pickInfos,
  RESULT_ATTRIBUTES,
} from "../chart/attributes";
import type { Manifest } from "../../project/lib/record-server/types";

const labels = (level: Level, inspect: boolean) =>
  statisticsFor(level, inspect).map((s) => s.label);

describe("statistics per level", () => {
  it("has none on a single entity or a global constraint", () => {
    expect(statisticsFor({ kind: "entity", entity: "g" }, true)).toEqual([]);
    expect(statisticsFor({ kind: "component", ctype: "GlobalConstraint" }, true)).toEqual([]);
  });

  it("says Starting in Build and Actual on a run result for capacity charts", () => {
    expect(labels({ kind: "all-entities" }, false)).toContain("Starting load vs renewables");
    expect(labels({ kind: "all-entities" }, true)).toContain("Actual load vs renewables");
  });

  it("marks run result statistics, which Build greys out", () => {
    const all = statisticsFor({ kind: "all-entities" }, false);
    expect(all.find((s) => s.base === "Dispatch by carrier")?.result).toBe(true);
    expect(all.find((s) => s.base === "Load duration curve")?.result).toBe(false);
  });

  it("drops capacity by carrier on a carrier level", () => {
    const level: Level = { kind: "carrier", ctype: "Generator", carrier: "solar" };
    expect(statisticsFor(level, false).some((s) => s.base === "Capacity by carrier")).toBe(false);
    expect(
      statisticsFor({ kind: "component", ctype: "Generator" }, false).some(
        (s) => s.base === "Capacity by carrier",
      ),
    ).toBe(true);
  });

  it("gives location levels their bus charts, with a price below All locations", () => {
    expect(labels({ kind: "all-locations" }, true)).not.toContain("Bus price");
    expect(labels({ kind: "location", location: "BE0" }, true)).toContain("Bus price");
    expect(labels({ kind: "bus", bus: "b", location: null }, true)).toContain("Bus price");
  });

  it("keeps base names unique within a level", () => {
    const levels: Level[] = [
      { kind: "all-entities" },
      { kind: "component", ctype: "Generator" },
      { kind: "component", ctype: "Line" },
      { kind: "all-locations" },
    ];
    for (const level of levels) {
      const bases = statisticsFor(level, true).map((s) => s.base);
      expect(new Set(bases).size).toBe(bases.length);
    }
  });
});

describe("attribute options", () => {
  const manifest = {
    attributes: {
      p_max_pu: { unit: "per unit", dims: ["entity"] },
      p: { unit: "MW", dims: ["connection"] },
      marginal_price: { unit: "EUR/MWh", dims: ["bus"] },
    },
  } as unknown as Manifest;

  it("lists inputs first, then results greyed in Build, adding results the level's types would have", () => {
    const options = attributeOptions(
      [{ ctype: "Generator", attribute: "p_max_pu", n: 3 }],
      ["Generator"],
      false,
      manifest,
      false,
    );
    expect(options.map((o) => o.id)).toEqual(["Generator · p_max_pu", "Generator · p"]);
    expect(options[1]).toMatchObject({ result: true, available: false, n: 0, dim: "connection" });
    expect(attributeOptions([], ["Generator"], false, manifest, true)[0].available).toBe(false);
  });

  it("adds a bus price at location levels", () => {
    const options = attributeOptions([], [], true, manifest, true);
    expect(options).toEqual([expect.objectContaining({ id: "Bus · marginal_price", dim: "bus" })]);
  });

  it("does not sum per unit values or prices", () => {
    expect(aggregationsFor("MW")).toEqual(["sum", "mean", "all", "each"]);
    expect(aggregationsFor("per unit")).toEqual(["mean", "all", "each"]);
    expect(aggregationsFor("EUR/MWh")).toEqual(["mean", "all", "each"]);
  });

  it("gives each picked series a colour in pick order and flags results", () => {
    const infos = pickInfos(
      [
        { entity: "g1", ctype: "Generator", attribute: "p_max_pu", bus: null, unit: null },
        { entity: "g2", ctype: "Generator", attribute: "p", bus: "b", unit: null },
      ],
      manifest,
    );
    expect(infos[0]).toMatchObject({ label: "p_max_pu · g1", unit: "per unit", result: false });
    expect(infos[1]).toMatchObject({ result: true, unit: "MW" });
    expect(infos[1].query).toMatchObject({ dim: "connection", bus: "b" });
    expect(infos[0].color).not.toBe(infos[1].color);
    expect(RESULT_ATTRIBUTES.has("p")).toBe(true);
  });
});
