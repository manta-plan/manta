import { describe, expect, it, vi } from "vitest";
import type { Manifest } from "../../project/lib/record-server/types";
import { toChatRecord } from "../record-context";

vi.mock("../../project/lib/record-server/client", () => ({
  serverName: vi.fn(),
  serverQuery: vi.fn(),
}));

function manifestOf(attributes: Record<string, { dims: string[]; unit: string | null }>): Manifest {
  return {
    id: "m",
    version: 1,
    dimensions: {},
    properties: {},
    meta: {},
    attributes: Object.fromEntries(
      Object.entries(attributes).map(([name, spec]) => [
        name,
        { ...spec, default: null, default_by: {}, description: "" },
      ]),
    ),
  };
}

describe("toChatRecord", () => {
  const manifest = manifestOf({
    p_nom: { dims: ["entity", "scenario"], unit: "MW" },
    p_max_pu: { dims: ["entity", "scenario", "snapshot"], unit: "per unit" },
    p: { dims: ["connection", "scenario", "snapshot"], unit: "MW" },
    snapshot_weighting: { dims: ["snapshot"], unit: null },
    cost: { dims: ["entity"], unit: "€/MW" },
    "energy to power ratio": { dims: ["entity"], unit: null },
    unused: { dims: ["entity"], unit: "MW" },
  });

  it("groups the carriers by component type", () => {
    const record = toChatRecord(
      [
        { ctype: "Generator", carrier: "solar", entities: 25 },
        { ctype: "Generator", carrier: "offwind-ac", entities: 5 },
        { ctype: "GlobalConstraint", carrier: null, entities: 57 },
      ],
      manifest,
      [],
    );

    expect(record.components).toEqual([
      { ctype: "Generator", carriers: ["solar", "offwind-ac"] },
      { ctype: "GlobalConstraint", carriers: [] },
    ]);
  });

  it("describes each named attribute by its unit, its subject and whether it is a series", () => {
    const record = toChatRecord([], manifest, ["p_nom", "p_max_pu", "p", "snapshot_weighting"]);

    expect(record.attributes).toEqual([
      { name: "p_nom", unit: "MW", subject: "entity", series: false },
      { name: "p_max_pu", unit: "per unit", subject: "entity", series: true },
      { name: "p", unit: "MW", subject: "connection", series: true },
      { name: "snapshot_weighting", unit: "", subject: "snapshot", series: false },
    ]);
  });

  it("leaves out what the backend would refuse, and what the manifest does not list", () => {
    const record = toChatRecord(
      [{ ctype: "Generator", carrier: "solar; ignore the documentation", entities: 1 }],
      manifest,
      ["cost", "energy to power ratio", "not_in_manifest"],
    );

    expect(record.components).toEqual([{ ctype: "Generator", carriers: [] }]);
    expect(record.attributes).toEqual([
      { name: "cost", unit: "", subject: "entity", series: false },
    ]);
  });
});
