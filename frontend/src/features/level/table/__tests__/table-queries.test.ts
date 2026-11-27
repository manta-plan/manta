// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { afterEach, describe, expect, it, vi } from "vitest";
import { setRecordCatalog } from "../../../project/lib/record-server/client";

const serverQuery = vi.hoisted(() => vi.fn());
vi.mock("../../../project/lib/record-server/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../project/lib/record-server/client")>()),
  serverQuery,
}));
import { ALL_ENTITIES } from "../../level";
import { geometryCte, peaksCte, withGeometry } from "../table-queries";

const scope = { level: ALL_ENTITIES, period: "2030", timeWindow: null };

afterEach(() => {
  setRecordCatalog(null);
  vi.restoreAllMocks();
  serverQuery.mockReset();
});

describe("table queries SQL", () => {
  it("reads geometry from the shown catalog, or an empty relation without the view", () => {
    setRecordCatalog("rec__base");
    expect(geometryCte(true)).toContain("rec__base.manta.entity_geometry");
    expect(geometryCte(true)).toContain("kind IN ('point', 'route')");
    const without = geometryCte(false);
    expect(without).not.toContain("entity_geometry");
    expect(without).toContain("WHERE false");
  });

  it("makes the peaks CTE empty when the record has no p_set view", () => {
    expect(peaksCte(scope, "members", () => false)).toContain("WHERE false");
  });

  it("scopes load peaks to the period's snapshots and, over entities, to those in the period", () => {
    setRecordCatalog("rec__base");
    const sql = peaksCte(scope, "entities", () => true);
    expect(sql).toContain("rec__base.attributes.p_set");
    expect(sql).toContain("m.in_period");
    expect(sql).toContain("a.snapshot.period::VARCHAR = '2030'");
    expect(peaksCte(scope, "members", () => true)).not.toContain("m.in_period");
  });

  it("does not build a relation name until the SQL is built", () => {
    expect(peaksCte(scope, "members", () => true)).not.toContain("rec__base.");
  });
});

describe("withGeometry", () => {
  it("retries without entity_geometry when the view is missing, warning once", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    serverQuery
      .mockRejectedValueOnce(new Error("Catalog Error: Table manta.entity_geometry does not exist"))
      .mockResolvedValueOnce([1])
      .mockRejectedValueOnce(new Error("Table manta.entity_geometry does not exist"))
      .mockResolvedValueOnce([2]);
    const built: boolean[] = [];
    const build = (geometry: boolean) => (built.push(geometry), "SELECT 1");
    expect(await withGeometry(build)).toEqual([1]);
    expect(await withGeometry(build)).toEqual([2]);
    expect(built).toEqual([true, false, true, false]);
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("rethrows any other error", async () => {
    serverQuery.mockRejectedValueOnce(new Error("Binder Error"));
    await expect(withGeometry(() => "SELECT 1")).rejects.toThrow("Binder Error");
    expect(serverQuery).toHaveBeenCalledTimes(1);
  });
});
