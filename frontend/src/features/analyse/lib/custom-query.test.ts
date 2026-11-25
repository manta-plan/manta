import { describe, expect, it } from "vitest";
import { parseQuerySql, querySql, type CustomQuery } from "./custom-query";
import type { ResultTableInfo } from "./result-source";

const table: ResultTableInfo = {
  name: "supply",
  label: "Supply",
  description: "",
  unit: "TWh",
  valueLabel: "Supply",
  columns: ["carrier", "bus"],
  kind: "energy",
  builtIn: true,
  defaultAggregate: "sum",
};

const queryWith = (values: string[]): CustomQuery => ({
  table: "supply",
  aggregate: "sum",
  groupBy: ["carrier"],
  where: [{ column: "bus", values }],
  orderBy: null,
  limit: null,
});

describe("parseQuerySql", () => {
  it.each(["wind--offshore", "North  Hub", "it's -- here"])(
    "reads back a quoted value that looks like a comment or has spacing: %s",
    (value) => {
      const parsed = parseQuerySql(querySql(queryWith([value])), [table]);
      expect(parsed).toEqual({ ok: true, query: queryWith([value]) });
    },
  );

  it("still drops comments outside quotes", () => {
    const parsed = parseQuerySql(
      "SELECT carrier, SUM(value) AS value -- the total\nFROM supply\nGROUP BY carrier",
      [table],
    );
    expect(parsed.ok).toBe(true);
  });
});
