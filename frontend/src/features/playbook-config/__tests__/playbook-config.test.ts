import { describe, expect, it } from "vitest";
import type { PlaybookDetail } from "../../../utils/playbookTypes";
import { collectGroups, groupLabel, resolveSchema, seedDefaults } from "../../../utils/jsonSchema";
import { buildConfig } from "../buildConfig";
import { deriveGlobalFields, isStepActive, linkedSource, setAtPath } from "../conditions";
import fixture from "../__fixtures__/cluster-expand-dispatch.json";
import { validateStep } from "../validation";

const playbook = fixture as unknown as PlaybookDetail;
const step = (name: string) => playbook.steps.find((item) => item.name === name)!;

describe("conditions", () => {
  it("overnight activates cluster, expansion_overnight and dispatch", () => {
    const active = playbook.steps.filter((s) => isStepActive(s, playbook.default_config));
    expect(active.map((s) => s.name)).toEqual(["cluster", "expansion_overnight", "dispatch"]);
  });

  it("myopic activates cluster and expansion_myopic", () => {
    const config = setAtPath(playbook.default_config, "globals.expansion_mode", "myopic");
    const active = playbook.steps.filter((s) => isStepActive(s, config));
    expect(active.map((s) => s.name)).toEqual(["cluster", "expansion_myopic"]);
  });

  it("derives the globals select from the when clauses", () => {
    expect(deriveGlobalFields(playbook)).toEqual([
      { path: "globals.expansion_mode", options: ["overnight", "myopic"] },
    ]);
  });

  it("parses a linked input source", () => {
    expect(linkedSource(step("dispatch"), "capacity_source")).toEqual({
      stepName: "expansion_overnight",
      field: "output",
    });
    expect(linkedSource(step("cluster"), "n_hours")).toBeNull();
  });
});

describe("schema resolution", () => {
  const schema = step("expansion_myopic").block_config_schema!;
  const defs = schema.$defs ?? {};
  const optimize = defs.PyPSAOptimizeSchema.properties!;

  it("reads a typed list as an array and an untyped one as json", () => {
    expect(resolveSchema("meshed_thresholds", optimize.meshed_thresholds, defs).kind).toBe("array");
    expect(resolveSchema("piecewise_options", optimize.piecewise_options, defs).kind).toBe("json");
  });

  it("reads a nullable $ref as a nullable object", () => {
    const resolved = resolveSchema("transmission_losses", optimize.transmission_losses, defs);
    expect(resolved.kind).toBe("object");
    expect(resolved.nullable).toBe(true);
  });

  it("seeds a nullable group from its defaults", () => {
    const seeded = seedDefaults(defs._PyPSAOptimizeTransmissionLossesSchema.properties!, defs);
    expect(seeded).toMatchObject({ mode: "secant", max_segments: 20 });
    expect(seeded).not.toHaveProperty("segments");
  });
});

describe("validation", () => {
  it("accepts the default config of every step", () => {
    for (const s of playbook.steps) {
      expect(validateStep(s, playbook.default_config[s.name] ?? {})).toEqual([]);
    }
  });

  it("rejects a decimal n_hours", () => {
    const errors = validateStep(step("cluster"), { n_hours: 2.5 });
    expect(errors.map((e) => e.path)).toContain("n_hours");
  });

  it("rejects an unknown key", () => {
    const errors = validateStep(step("cluster"), { nope: 1 });
    expect(errors.map((e) => e.path)).toContain("nope");
  });

  it("does not require a linked input", () => {
    expect(validateStep(step("dispatch"), {})).toEqual([]);
  });
});

describe("buildConfig", () => {
  it("keeps the default config as it is", () => {
    expect(buildConfig(playbook, playbook.default_config)).toEqual(playbook.default_config);
  });

  it("drops unknown, const and linked keys but keeps every step", () => {
    const config = {
      ...playbook.default_config,
      cluster: { n_hours: 2, bogus: 1 },
      expansion_overnight: { optimize_config: { solver_name: "highs", assign_all_duals: true } },
      dispatch: { capacity_source: "x" },
    };
    const built = buildConfig(playbook, config);
    expect(built.cluster).toEqual({ n_hours: 2 });
    expect(built.expansion_overnight).toEqual({ optimize_config: { assign_all_duals: true } });
    expect(built.dispatch).toEqual({});
    expect(Object.keys(built)).toEqual(Object.keys(config));
  });

  it("keeps an explicit null", () => {
    const built = buildConfig(playbook, { ...playbook.default_config, cluster: { n_hours: null } });
    expect(built.cluster).toEqual({ n_hours: null });
  });
});

describe("group labels", () => {
  const label = (name: string, key: string, path: string[] = []) => {
    const schema = step(name).block_config_schema!;
    const defs = schema.$defs ?? {};
    let properties = schema.properties!;
    let property = properties[key];

    for (const next of path) {
      properties = resolveSchema(key, property, defs).schema.properties!;
      property = properties[next];
      key = next;
    }

    return groupLabel(resolveSchema(key, property, defs));
  };

  it("has no groups when a block has no $defs", () => {
    const schema = step("cluster").block_config_schema!;
    expect(schema.$defs).toBeUndefined();
    for (const [key, property] of Object.entries(schema.properties!)) {
      expect(resolveSchema(key, property, {}).kind).not.toBe("object");
    }
  });

  it("names groups after the def, not the property", () => {
    for (const name of ["expansion_overnight", "expansion_myopic"]) {
      expect(label(name, "optimize_config")).toBe("PyPSAOptimizeSchema Config");
    }
    // dispatch declares its own def for the same property: nothing is shared by name.
    expect(label("dispatch", "optimize_config")).toBe("PyPSAOptimizeRollingHorizonConfig Config");

    for (const name of ["expansion_overnight", "expansion_myopic", "dispatch"]) {
      expect(label(name, "optimize_config", ["model_kwargs"])).toBe("LinopyModelSchema Config");
    }
  });

  it("reads the def through a nullable anyOf and drops a leading underscore", () => {
    expect(label("expansion_myopic", "optimize_config", ["transmission_losses"])).toBe(
      "PyPSAOptimizeTransmissionLossesSchema Config",
    );
  });

  it("follows whatever defs a block declares", () => {
    const defs = {
      FooSchema: { type: "object" as const, properties: { a: { type: "string" as const } } },
    };
    const resolved = resolveSchema("foo", { $ref: "#/$defs/FooSchema" }, defs);
    expect(groupLabel(resolved)).toBe("FooSchema Config");
  });

  it("keeps the property's own label for an inline object", () => {
    const resolved = resolveSchema(
      "inline_thing",
      { type: "object", title: "Inline Thing", properties: { a: { type: "string" } } },
      {},
    );
    expect(groupLabel(resolved)).toBe("Inline Thing");
  });
});

describe("collectGroups", () => {
  const groupsOf = (name: string) => {
    const schema = step(name).block_config_schema!;
    return collectGroups(schema.properties ?? {}, schema.$defs ?? {});
  };

  it("makes every def its own flat group in dispatch", () => {
    expect(groupsOf("dispatch").map((g) => [g.path.join("/"), groupLabel(g.resolved)])).toEqual([
      ["capacity_source", "DataRecord Config"],
      ["optimize_config", "PyPSAOptimizeRollingHorizonConfig Config"],
      ["optimize_config/model_kwargs", "LinopyModelSchema Config"],
      ["optimize_config/transmission_losses", "PyPSAOptimizeTransmissionLossesSchema Config"],
    ]);
  });

  it("marks capacity_source as linked", () => {
    expect(groupsOf("dispatch")[0].linked).toBe(true);
  });

  it("gives expansion steps three groups and cluster none", () => {
    expect(groupsOf("expansion_overnight")).toHaveLength(3);
    expect(groupsOf("expansion_myopic")).toHaveLength(3);
    expect(groupsOf("cluster")).toHaveLength(0);
  });
});
