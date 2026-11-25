// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import {
  getActiveProjectTab,
  projectAnalyseHref,
  projectInspectHref,
  projectRecordPageHref,
  projectRunHref,
  projectTabHref,
} from "./project-route";

describe("project routes", () => {
  it("reads the tab from the address", () => {
    expect(getActiveProjectTab("/project/p1")).toBe("build");
    expect(getActiveProjectTab("/project/p1/build")).toBe("build");
    expect(getActiveProjectTab("/project/p1/build/entity:x")).toBe("build");
    expect(getActiveProjectTab("/project/p1/run")).toBe("run");
    expect(getActiveProjectTab("/project/p1/run/abc")).toBe("run");
    expect(getActiveProjectTab("/project/p1/inspect")).toBe("inspect");
    expect(getActiveProjectTab("/project/p1/inspect/component:Generator")).toBe("inspect");
    expect(getActiveProjectTab("/project/p1/analyse")).toBe("analyse");
    expect(getActiveProjectTab("/project/p1/inspect?scenario=a/b")).toBe("inspect");
  });

  it("builds the tab and page addresses", () => {
    expect(projectTabHref("p1", "build")).toBe("/project/p1/build");
    expect(projectRunHref("p1", "r1")).toBe("/project/p1/run/r1");
    expect(projectInspectHref("p1")).toBe("/project/p1/inspect");
    expect(projectRecordPageHref("p1", "inspect", "locations")).toBe(
      "/project/p1/inspect/locations",
    );
    expect(projectRecordPageHref("p1", "build", null)).toBe("/project/p1/build");
    expect(projectAnalyseHref("p1")).toBe("/project/p1/analyse");
  });
});
