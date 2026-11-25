// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import fixture from "../../playbook-config/__fixtures__/cluster-expand-dispatch.json";
import { setAtPath } from "../../playbook-config/conditions";
import type { PlaybookDetail } from "../../../utils/playbookTypes";
import {
  describeStepErrors,
  getActiveSteps,
  getRunsPanelEmptyMessage,
  getStepErrors,
  toMessage,
} from "../run-draft";

const playbook = fixture as unknown as PlaybookDetail;

describe("getActiveSteps", () => {
  it("lists the steps that run, in step order", () => {
    expect(getActiveSteps(playbook, playbook.default_config).map((step) => step.name)).toEqual([
      "cluster",
      "expansion_overnight",
      "dispatch",
    ]);
  });

  it("follows a global field", () => {
    const config = setAtPath(playbook.default_config, "globals.expansion_mode", "myopic");

    expect(getActiveSteps(playbook, config).map((step) => step.name)).toEqual([
      "cluster",
      "expansion_myopic",
    ]);
  });
});

describe("getStepErrors", () => {
  it("is empty for the default config", () => {
    expect(getStepErrors(playbook, playbook.default_config).size).toBe(0);
  });

  it("flags an invalid active step", () => {
    const config = { ...playbook.default_config, cluster: { n_hours: 2.5 } };

    expect([...getStepErrors(playbook, config).keys()]).toEqual(["cluster"]);
  });

  it("ignores a step that does not run", () => {
    const config = setAtPath(
      { ...playbook.default_config, expansion_overnight: { nope: 1 } },
      "globals.expansion_mode",
      "myopic",
    );

    expect(getStepErrors(playbook, config).has("expansion_overnight")).toBe(false);
  });
});

describe("describeStepErrors", () => {
  it("is null without errors", () => {
    expect(describeStepErrors(new Map())).toBeNull();
  });

  it("names the steps to resolve", () => {
    const errors = new Map([
      ["cluster", [{ path: "n_hours", message: "x" }]],
      ["expansion_overnight", [{ path: "a", message: "y" }]],
    ]);

    expect(describeStepErrors(errors)).toBe(
      "Resolve the settings of Cluster, Expansion Overnight before starting the run.",
    );
  });
});

describe("toMessage", () => {
  it("capitalises an error message", () => {
    expect(toMessage(new Error("failed to fetch"), "fallback")).toBe("Failed to fetch");
  });

  it("falls back for an empty message or a non-error", () => {
    expect(toMessage(new Error(""), "fallback")).toBe("fallback");
    expect(toMessage("boom", "fallback")).toBe("fallback");
    expect(toMessage(null, "fallback")).toBe("fallback");
  });
});

describe("getRunsPanelEmptyMessage", () => {
  it("is null when there are rows", () => {
    expect(getRunsPanelEmptyMessage({ hasRows: true, isFiltered: true })).toBeNull();
  });

  it("asks to create a run when there are none", () => {
    expect(getRunsPanelEmptyMessage({ hasRows: false, isFiltered: false })).toBe(
      "No runs yet — create one to get started.",
    );
  });

  it("says the filters match nothing", () => {
    expect(getRunsPanelEmptyMessage({ hasRows: false, isFiltered: true })).toBe(
      "No runs match the current filters.",
    );
  });
});
