// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from "vitest";
import {
  columnSeries,
  columnStatistics,
  filterAndSort,
  filterKind,
  MAX_LISTED_VALUES,
  passes,
  SERIES_VALUE,
  type CellValue,
  type TableColumn,
} from "../columns";
import { formatCell } from "../format";
import { locationColumns, mixedColumns, type ColumnContext } from "../level-columns";
import { ALL_ENTITIES } from "../../level";
import type { Manifest } from "../../../project/lib/record-server/types";
import type { LocationRow, MixedRow } from "../table-queries";
import type { ColumnFilter } from "../../level-store";

interface Row {
  id: string;
  n: number | null;
  t: string | null;
}

const column = (kind: TableColumn<Row>["kind"], key: "n" | "t"): TableColumn<Row> => ({
  key,
  header: key,
  kind,
  value: (row) => row[key] as CellValue,
  render: () => null,
});
const rows: Row[] = [
  { id: "a", n: 3, t: "wind" },
  { id: "b", n: null, t: "solar" },
  { id: "c", n: 1, t: "wind" },
  { id: "d", n: 10, t: null },
];
const columns = [column("number", "n"), column("text", "t")];

describe("format", () => {
  it("rounds a cell to what the eye can use, with a dash for none", () => {
    expect(formatCell(null)).toBe("—");
    expect(formatCell(NaN)).toBe("—");
    expect(formatCell(1.2345)).toBe("1.2");
    expect(formatCell(1234.6)).toBe("1,235");
    expect(formatCell(0.0123, 3)).toBe("0.012");
  });
});

describe("filter", () => {
  it("passes a number inside a range, open at either end; not a non-number", () => {
    const range = (min: number | null, max: number | null): ColumnFilter => ({
      kind: "range",
      min,
      max,
    });
    expect(passes(range(2, 5), 3)).toBe(true);
    expect(passes(range(2, 5), 6)).toBe(false);
    expect(passes(range(2, null), 99)).toBe(true);
    expect(passes(range(2, 5), null)).toBe(false);
    expect(passes(range(null, null), null)).toBe(true);
  });

  it("passes listed values, with an empty value as the empty string", () => {
    const filter: ColumnFilter = { kind: "values", values: ["wind", ""] };
    expect(passes(filter, "wind")).toBe(true);
    expect(passes(filter, null)).toBe(true);
    expect(passes(filter, "solar")).toBe(false);
  });

  it("matches a substring without regard to case", () => {
    expect(passes({ kind: "contains", text: "WIN" }, "wind")).toBe(true);
    expect(passes({ kind: "contains", text: "x" }, null)).toBe(false);
    expect(passes({ kind: "contains", text: "" }, null)).toBe(true);
    expect(passes(undefined, null)).toBe(true);
  });

  it("filters rows by every column's filter, hidden columns too", () => {
    const kept = filterAndSort(
      rows,
      columns,
      { t: { kind: "values", values: ["wind"] }, n: { kind: "range", min: 2, max: null } },
      null,
    );
    expect(kept.map((row) => row.id)).toEqual(["a"]);
  });
});

describe("sort", () => {
  it("sorts ascending and descending with empties last either way", () => {
    const asc = filterAndSort(rows, columns, {}, { column: "n", direction: "asc" });
    expect(asc.map((row) => row.id)).toEqual(["c", "a", "d", "b"]);
    const desc = filterAndSort(rows, columns, {}, { column: "n", direction: "desc" });
    expect(desc.map((row) => row.id)).toEqual(["d", "a", "c", "b"]);
  });

  it("sorts text naturally (BE2 before BE10)", () => {
    const named = [{ id: "BE10" }, { id: "BE2" }];
    const col: TableColumn<{ id: string }> = {
      key: "id",
      header: "id",
      kind: "text",
      value: (row) => row.id,
      render: () => null,
    };
    expect(
      filterAndSort(named, [col], {}, { column: "id", direction: "asc" }).map((row) => row.id),
    ).toEqual(["BE2", "BE10"]);
  });

  it("keeps the input order with no sort or an unknown column, and does not mutate", () => {
    expect(filterAndSort(rows, columns, {}, null)).toEqual(rows);
    expect(filterAndSort(rows, columns, {}, { column: "zzz", direction: "asc" })).toEqual(rows);
  });
});

describe("filterKind", () => {
  it("filters numbers by range", () => {
    expect(filterKind(columns[0], rows)).toEqual({ kind: "range" });
  });

  it("lists text values by count, then name", () => {
    expect(filterKind(columns[1], rows)).toEqual({
      kind: "values",
      counts: [
        ["wind", 2],
        ["", 1],
        ["solar", 1],
      ],
    });
  });

  it("falls back to Contains past the listing limit for text, not for series", () => {
    const many = Array.from({ length: MAX_LISTED_VALUES + 5 }, (_, i) => ({
      id: String(i),
      n: i,
      t: `v${i}`,
    }));
    expect(filterKind(column("text", "t"), many)).toEqual({ kind: "contains" });
    expect(filterKind(column("series", "t"), many).kind).toBe("values");
  });
});

describe("statistics", () => {
  it("summarises numbers over the rows given, counting missing", () => {
    const stats = columnStatistics(columns[0], rows);
    if (stats.kind !== "number") throw new Error("expected number statistics");
    expect(stats).toMatchObject({ n: 4, min: 1, max: 10, median: 3, unique: 3, missing: 1 });
    expect(stats.mean).toBeCloseTo(14 / 3);
    expect(stats.p25).toBe(2);
    expect(stats.p75).toBe(6.5);
    expect(stats.bins.reduce((a, b) => a + b, 0)).toBe(3);
    expect(stats.bins[stats.bins.length - 1]).toBe(1);
  });

  it("puts equal numbers in the first bin", () => {
    const stats = columnStatistics(columns[0], [{ id: "x", n: 5, t: null }]);
    if (stats.kind !== "number") throw new Error("expected number statistics");
    expect(stats.bins[0]).toBe(1);
  });

  it("says empty when there is no number, and counts the top text values", () => {
    expect(columnStatistics(columns[0], [{ id: "x", n: null, t: null }])).toEqual({
      kind: "empty",
      n: 1,
    });
    expect(columnStatistics(columns[1], rows)).toEqual({
      kind: "text",
      n: 4,
      unique: 3,
      top: [
        ["wind", 2],
        ["solar", 1],
        ["", 1],
      ],
    });
    expect(columnStatistics(columns[1], [rows[0], rows[1]])).toMatchObject({ top: [] });
  });
});

describe("columnSeries", () => {
  const series = (attribute: string, ctype = "Generator") => ({
    entity: "e",
    ctype,
    attribute,
    bus: null,
    unit: null,
  });
  const col: TableColumn<Row> = {
    ...columns[1],
    kind: "series",
    series: (row) => (row.t ? series(row.t) : null),
  };
  it("counts series and names the one attribute they share", () => {
    expect(columnSeries(col, [rows[0], rows[2], rows[1]])).toEqual({ count: 3, attribute: null });
    expect(columnSeries(col, [rows[0], rows[2]])).toEqual({
      count: 2,
      attribute: "Generator · wind",
    });
    expect(columnSeries(columns[0], rows)).toEqual({ count: 0, attribute: null });
  });
});

// ---- Columns per level

const manifest = {
  attributes: { p_nom: { unit: "MW", dtype: "float" }, p_max_pu: { unit: null, dtype: "float" } },
} as unknown as Manifest;

const context = (inspect: boolean): ColumnContext => ({
  level: ALL_ENTITIES,
  inspect,
  hours: 168,
  period: "2030",
  carrier: (carrier) => ({ name: carrier ?? "—", color: null }),
  openLevel: () => {},
  manifest,
  changes: null,
  parentLabel: "base",
  results: new Set(),
  regionOf: () => null,
});

const mixed: MixedRow = {
  entity: "gen 1",
  ctype: "Generator",
  carrier: "solar",
  bus: "BE0 0",
  bus1: null,
  location: "BE0 0",
  location1: null,
  cap_attribute: "p_nom",
  capacity: 100,
  capacity_opt: 120,
  status: null,
  geometry: "point",
  profile: "p_max_pu",
  profile_constant: null,
  profile_rows: 8760,
  peak: null,
  dispatch_rows: 8760,
};

describe("columns per level", () => {
  it("gives a mixed level its entity columns, capacity and profile; Inspect adds results", () => {
    const build = mixedColumns(context(false), [mixed]);
    expect(build.map((c) => c.key)).toEqual([
      "entity",
      "ctype",
      "carrier",
      "location",
      "bus",
      "geolocated",
      "capacity",
      "profile",
    ]);
    const inspect = mixedColumns(context(true), [mixed]);
    expect(inspect.slice(-2).map((c) => c.key)).toEqual(["optimised", "dispatch"]);
  });

  it("reads a load's capacity as its peak, and a series profile as a chip value", () => {
    const [capacity, profile] = mixedColumns(context(false), [mixed]).slice(-2);
    expect(capacity.value(mixed)).toBe(100);
    expect(capacity.value({ ...mixed, ctype: "Load", peak: 55 })).toBe(55);
    expect(profile.value(mixed)).toBe(SERIES_VALUE);
    expect(profile.series?.(mixed)).toMatchObject({ entity: "gen 1", attribute: "p_max_pu" });
    const constant = { ...mixed, profile_rows: 0, profile_constant: "0.9" };
    expect(profile.series?.(constant)).toBeNull();
    expect(profile.value(constant)).toBe("0.9");
  });

  it("shows no Status column unless some row has one, and Geolocated reads site or route", () => {
    expect(mixedColumns(context(false), [mixed]).some((c) => c.key === "status")).toBe(false);
    const withStatus = mixedColumns(context(false), [{ ...mixed, status: "existing" }]);
    expect(withStatus.some((c) => c.key === "status")).toBe(true);
    const geo = withStatus.find((c) => c.key === "geolocated")!;
    expect(geo.value(mixed)).toBe("site");
    expect(geo.value({ ...mixed, geometry: "route" })).toBe("route");
    expect(geo.value({ ...mixed, geometry: null })).toBeNull();
  });

  it("makes a location table with a region, buses count and, on Inspect, the price series", () => {
    const location: LocationRow = {
      location: "BE0 0",
      buses: [{ bus: "BE0 0", carrier: "AC" }],
      entities: 4,
      located: 2,
      gen_capacity: 10,
      gen_capacity_opt: 12,
      peak_demand: 5,
      lines: 1,
      demand_load: "load 1",
      price_bus: "BE0 0",
    };
    const build = locationColumns(context(false));
    expect(build.map((c) => c.key)).not.toContain("marginal_price");
    expect(build.find((c) => c.key === "buses")!.value(location)).toBe(1);
    expect(build.find((c) => c.key === "demand")!.series?.(location)).toMatchObject({
      entity: "load 1",
      attribute: "p_set",
    });
    const inspect = locationColumns(context(true));
    expect(inspect.find((c) => c.key === "marginal_price")!.series?.(location)).toMatchObject({
      ctype: "Bus",
      attribute: "marginal_price",
    });
  });
});
