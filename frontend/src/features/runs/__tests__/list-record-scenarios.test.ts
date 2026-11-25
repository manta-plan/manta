// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import type { Revision } from "../../project/lib/record-server/types";
import { listRecordScenarios } from "../list-record-scenarios";

function revision(name: string, parent: string | null, kind: Revision["kind"] = "scenario") {
  return {
    name,
    id: name,
    parent,
    kind,
    label: name,
    description: "",
    catalog: null,
    open: false,
    results: [],
  };
}

describe("listRecordScenarios", () => {
  it("is empty without scenarios", () => {
    expect(listRecordScenarios([])).toEqual([]);
    expect(listRecordScenarios([revision("r", null, "result")])).toEqual([]);
  });

  it("leaves results out", () => {
    const names = listRecordScenarios([revision("base", null), revision("run", "base", "result")]);

    expect(names.map((item) => item.name)).toEqual(["base"]);
  });

  it("lists a parent before the scenarios that start from it", () => {
    const names = listRecordScenarios([
      revision("grandchild", "child"),
      revision("child", "base"),
      revision("base", null),
    ]);

    expect(names.map((item) => item.name)).toEqual(["base", "child", "grandchild"]);
  });

  it("does not loop on a cycle", () => {
    const names = listRecordScenarios([revision("a", "b"), revision("b", "a")]);

    expect(names).toHaveLength(2);
  });
});
