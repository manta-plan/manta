// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { mergeBackendProjects, withoutLocalProjects, type Project } from "../store";

const project = (id: string, extra: Partial<Project> = {}): Project => ({
  id,
  name: id,
  lastModified: "Just now",
  ...extra,
});

describe("withoutLocalProjects", () => {
  it("drops projects with a local id", () => {
    const result = withoutLocalProjects([project("project-1700000000000"), project("uuid-a")]);

    expect(result.map((item) => item.id)).toEqual(["uuid-a"]);
  });

  it("handles an empty list", () => {
    expect(withoutLocalProjects([])).toEqual([]);
  });
});

describe("mergeBackendProjects", () => {
  const backend = (uuid: string) => ({
    uuid,
    name: `Name ${uuid}`,
    description: null,
    updated_at: "2026-01-01T00:00:00Z",
  });

  it("drops local-only projects and projects the backend no longer has", () => {
    const result = mergeBackendProjects(
      [project("project-1"), project("gone"), project("uuid-a")],
      [backend("uuid-a")],
    );

    expect(result.map((item) => item.id)).toEqual(["uuid-a"]);
    expect(result[0].name).toBe("Name uuid-a");
  });

  it("keeps the browser-only record and welcome flag", () => {
    const [merged] = mergeBackendProjects(
      [project("uuid-a", { recordId: "rec", showWelcome: true })],
      [backend("uuid-a")],
    );

    expect(merged.recordId).toBe("rec");
    expect(merged.showWelcome).toBe(true);
  });

  it("returns nothing for an empty backend list", () => {
    expect(mergeBackendProjects([project("uuid-a")], [])).toEqual([]);
  });
});
