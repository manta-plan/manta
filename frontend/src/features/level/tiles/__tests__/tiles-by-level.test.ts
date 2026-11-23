// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { describe, expect, it, vi } from "vitest";
import { ALL_ENTITIES, ALL_LOCATIONS, type Level } from "../../level";
import { levelTiles, type Source, type TileContext } from "../tiles-by-level";
import type { Group, TileInputs, TileResults } from "../tile-queries";

const group = (over: Partial<Group>): Group => ({
  ctype: "Generator",
  carrier: "wind",
  color: "#00f",
  name: "Wind",
  entities: 2,
  existing: 1,
  candidate: 1,
  capacity: 100,
  actual: 150,
  new_build: 50,
  largest: "g1",
  largest_capacity: 60,
  largest_actual: "g2",
  largest_actual_capacity: 90,
  ...over,
});

const inputs = (over: Partial<TileInputs> = {}): TileInputs => ({
  hours: { span_hours: 100, period_hours: 8760 },
  counts: { active: 3, not_active: 1, existing: 2, candidate: 1, with_status: 3 },
  groups: [group({})],
  volumes: null,
  entity: null,
  load: null,
  capacityFactor: { estimate: 0.3, with_profile: 1, generators: 1 },
  storeEfficiency: null,
  locations: null,
  ...over,
});

const ready = <T>(data: T): Source<T> => ({ status: "ready", data });

function ctx(level: Level, over: Partial<TileContext> = {}): TileContext {
  return {
    level,
    results: false,
    stage: "build",
    period: "2030",
    windowLabel: "full span",
    inputs: ready(inputs()),
    runResults: null,
    open: vi.fn(),
    ...over,
  };
}

const generators: Level = { kind: "component", ctype: "Generator" };

describe("tiles by level", () => {
  it("shows one loading tile per slot while the inputs load", () => {
    const tiles = levelTiles(ctx(generators, { inputs: { status: "loading" } }));
    expect(tiles.length).toBeGreaterThan(0);
    expect(tiles.filter((t) => t.loading).length).toBeGreaterThan(0);
  });

  it("shows a dash with the error as its tooltip when the read failed", () => {
    const tiles = levelTiles(ctx(generators, { inputs: { status: "error", error: "boom" } }));
    const first = tiles[0];
    expect(first.value).toBe("—");
    expect(first.title).toBe("boom");
  });

  it("says Starting on Build and Actual on Inspect", () => {
    const build = levelTiles(ctx(generators)).find((t) => t.key === "capacity-factor")!;
    expect(build.label).toBe("Starting mean capacity factor");
    const results: TileResults = {
      hours: { span_hours: 100, period_hours: 8760 },
      flows: [],
      generators: null,
      stores: null,
    };
    const inspect = levelTiles(
      ctx(generators, { results: true, stage: "inspect", runResults: ready(results) }),
    ).find((t) => t.key === "capacity-factor")!;
    expect(inspect.label).toBe("Actual mean capacity factor");
  });

  it("marks result tiles unavailable on Build", () => {
    const tile = levelTiles(ctx(generators)).find((t) => t.key === "curtailment")!;
    expect(tile.value).toBe("—");
    expect(tile.detail).toBe("Available in Inspect");
  });

  it("scales a window's hour sum to a year", () => {
    const results: TileResults = {
      hours: { span_hours: 100, period_hours: 8760 },
      flows: [],
      generators: {
        generation: 0,
        available: 1000,
        curtailed: 100,
        market_value: 50,
        mean_price: 40,
      },
      stores: null,
    };
    const tile = levelTiles(
      ctx(generators, { results: true, stage: "inspect", runResults: ready(results) }),
    ).find((t) => t.key === "curtailment")!;
    expect(tile.value).toBe("10.0%");
    // 100 MWh over 100 h stands for 8,760 MWh a year.
    expect(tile.detail).toBe("8.76 GWh a year");
  });

  it("opens the type and the largest entity on click", () => {
    const open = vi.fn();
    const tiles = levelTiles(ctx(ALL_ENTITIES, { open }));
    tiles.find((t) => t.key === "capacity-Generator")!.onOpen!();
    expect(open).toHaveBeenCalledWith({ kind: "component", ctype: "Generator" });
  });

  it("leaves out tiles for what the level has none of", () => {
    const keys = levelTiles(ctx(ALL_ENTITIES)).map((t) => t.key);
    expect(keys).toContain("active");
    expect(keys).not.toContain("peak-load");
    expect(keys).not.toContain("storage-volume");
  });

  it("shows locations and buses at All locations", () => {
    const locations = {
      count: 5,
      buses: [{ carrier: "AC", buses: 7 }],
      regions: { level: "country", zones: 2 },
    };
    const tiles = levelTiles(ctx(ALL_LOCATIONS, { inputs: ready(inputs({ locations })) }));
    expect(tiles.find((t) => t.key === "locations")).toMatchObject({
      value: "5",
      detail: "substations in 2 country regions",
    });
    expect(tiles.find((t) => t.key === "buses")).toMatchObject({ value: "7", detail: "AC 7" });
  });

  it("says when the entity is not active in the period", () => {
    const tiles = levelTiles(ctx({ kind: "entity", entity: "g1" }));
    expect(tiles).toHaveLength(1);
    expect(tiles[0].detail).toBe("Not active in 2030");
  });
});
