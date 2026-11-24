import { beforeEach, describe, expect, it, vi } from "vitest";
import { recordCatalog, serverQuery } from "../../project/lib/record-server/client";
import { prepareSql, runSql, splitSqlReply, sqlErrorMessage } from "../run-sql";

vi.mock("../../project/lib/record-server/client", () => ({
  recordCatalog: vi.fn(),
  serverQuery: vi.fn(),
}));

const mockedCatalog = vi.mocked(recordCatalog);
const mockedServerQuery = vi.mocked(serverQuery);

beforeEach(() => {
  vi.resetAllMocks();
  mockedCatalog.mockReturnValue("bel__inputs");
});

describe("splitSqlReply", () => {
  it("finds the query in a sql block, with the text around it", () => {
    const reply = "Here it is:\n```sql\nSELECT 1 AS one\n```\nThe table shows one.";

    expect(splitSqlReply(reply)).toEqual({
      before: "Here it is:",
      sql: "SELECT 1 AS one",
      after: "The table shows one.",
    });
  });

  it("accepts a block without a language, when it holds a query", () => {
    expect(splitSqlReply("```\nWITH a AS (SELECT 1) FROM a\n```")?.sql).toBe(
      "WITH a AS (SELECT 1) FROM a",
    );
  });

  it("accepts a reply that starts with a query and has no block", () => {
    expect(splitSqlReply("SELECT ctype\nFROM properties.entity\n\nThe table shows types.")).toEqual(
      {
        before: "",
        sql: "SELECT ctype\nFROM properties.entity",
        after: "The table shows types.",
      },
    );
  });

  it("finds no query in a plain answer, or in a block of something else", () => {
    expect(splitSqlReply("Select New run on the Run tab.")).toBeNull();
    expect(splitSqlReply("Run this:\n```\nuv run manta\n```")).toBeNull();
  });
});

describe("prepareSql", () => {
  it("reads the given catalog and cuts the result off after the row limit", () => {
    const statement = prepareSql(
      "SELECT e.carrier FROM attributes.p_nom a JOIN properties.entity e USING (entity);",
      "bel__inputs",
    );

    expect(statement).toBe(
      "SELECT * FROM (\nSELECT e.carrier FROM bel__inputs.attributes.p_nom a JOIN bel__inputs.properties.entity e USING (entity)\n) LIMIT 201",
    );
  });

  it("leaves a name that already has a catalog, or is quoted, as it is", () => {
    const statement = prepareSql(
      'SELECT * FROM other.attributes.p_nom, "attributes".p_nom',
      "bel__inputs",
    );

    expect(statement).toContain('FROM other.attributes.p_nom, "attributes".p_nom');
  });

  it.each([
    ["two statements", "SELECT 1; DROP TABLE x"],
    ["a statement that is no query", "DROP TABLE attributes.p_nom"],
    ["an ATTACH", "ATTACH 'https://example.org/x.duckdb' AS x"],
    ["the quote serverQuery wraps the query in", "SELECT $$ || 'x'"],
  ])("refuses %s", (_, sql) => {
    expect(() => prepareSql(sql, "bel__inputs")).toThrow();
  });

  it("refuses to run without an open record", () => {
    expect(() => prepareSql("SELECT 1", "")).toThrow("No data record is open.");
  });

  it("keeps a trailing comment from swallowing the closing bracket", () => {
    expect(prepareSql("SELECT 1 -- one", "bel__inputs")).toBe(
      "SELECT * FROM (\nSELECT 1 -- one\n) LIMIT 201",
    );
  });
});

describe("runSql", () => {
  it("runs the prepared query on the record server and returns its rows", async () => {
    mockedServerQuery.mockResolvedValue([{ carrier: "solar", capacity_mw: 9752 }]);

    const result = await runSql("SELECT carrier, capacity_mw FROM manta.x");

    expect(mockedServerQuery).toHaveBeenCalledWith(
      "SELECT * FROM (\nSELECT carrier, capacity_mw FROM bel__inputs.manta.x\n) LIMIT 201",
    );
    expect(result).toEqual({
      columns: ["carrier", "capacity_mw"],
      rows: [{ carrier: "solar", capacity_mw: 9752 }],
      truncated: false,
    });
  });

  it("keeps the first 200 rows of a longer result and says so", async () => {
    mockedServerQuery.mockResolvedValue(Array.from({ length: 201 }, (_, n) => ({ n })));

    const result = await runSql("SELECT n FROM manta.x");

    expect(result.rows).toHaveLength(200);
    expect(result.truncated).toBe(true);
  });

  it("does not send a refused query to the server", async () => {
    await expect(runSql("DELETE FROM manta.x")).rejects.toThrow("Only a SELECT query can run.");
    expect(mockedServerQuery).not.toHaveBeenCalled();
  });
});

describe("sqlErrorMessage", () => {
  it("shortens a long error", () => {
    expect(sqlErrorMessage(new Error(`Binder Error: ${"x".repeat(900)}`))).toHaveLength(500);
  });
});
