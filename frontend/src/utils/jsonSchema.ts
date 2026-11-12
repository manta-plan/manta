import type { Defs, JsonSchemaProperty } from "./playbookTypes";

export type SchemaKind =
  | "integer"
  | "number"
  | "boolean"
  | "string"
  | "enum"
  | "object"
  | "array"
  | "json";

export type ResolvedSchema = {
  kind: SchemaKind;
  /** The schema with `$ref` followed and `X | None` unwrapped to `X`. */
  schema: JsonSchemaProperty;
  nullable: boolean;
  label: string;
  description: string | null;
  defaultValue: unknown;
  hasDefault: boolean;
  /** The `$defs` entry the property points at (`LinopyModelSchema`), if it does. */
  defName: string | null;
};

/** `expansion_mode` -> "Expansion Mode". */
export function humanize(key: string): string {
  return key
    .split("_")
    .filter((word) => word.length > 0)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

function followRef(property: JsonSchemaProperty, defs: Defs): JsonSchemaProperty {
  if (property.$ref === undefined) {
    return property;
  }

  const target = defs[property.$ref.split("/").pop() ?? ""];
  const { $ref: _ref, ...rest } = property;

  return target === undefined ? rest : { ...target, ...rest };
}

// "#/$defs/_Foo" -> "Foo". Leading underscores are Python's "private", not a name.
function refName(ref: string): string {
  return (ref.split("/").pop() ?? "").replace(/^_+/, "");
}

// The def a property points at, directly or as the one non-null branch of `X | None`.
function defNameOf(property: JsonSchemaProperty): string | null {
  if (property.$ref !== undefined) {
    return refName(property.$ref) || null;
  }

  const branches = (property.anyOf ?? []).filter((variant) => !isNullSchema(variant));

  return branches.length === 1 ? defNameOf(branches[0]) : null;
}

/** What a nested group of settings is called: its def ("LinopyModelSchema Config"), else its label. */
export function groupLabel(resolved: ResolvedSchema): string {
  return resolved.defName === null ? resolved.label : `${resolved.defName} Config`;
}

function isNullSchema(property: JsonSchemaProperty): boolean {
  return property.type === "null";
}

/**
 * Works out how to edit one property of a block's config schema: which kind of
 * input it needs, whether it can be null, and what it is called. `key` is the
 * config key (`n_hours`), the title is only a label ("N Hours").
 */
export function resolveSchema(
  key: string,
  property: JsonSchemaProperty,
  defs: Defs,
): ResolvedSchema {
  let schema = followRef(property, defs);
  let nullable = false;
  let unsupported = false;

  if (schema.anyOf !== undefined) {
    const variants = schema.anyOf.map((variant) => followRef(variant, defs));
    const nonNull = variants.filter((variant) => !isNullSchema(variant));
    nullable = nonNull.length < variants.length;

    if (nonNull.length === 1) {
      schema = { ...nonNull[0], ...omitAnyOf(schema) };
    } else {
      unsupported = true;
    }
  }

  const type = Array.isArray(schema.type) ? undefined : schema.type;
  let kind: SchemaKind;

  if (unsupported) {
    kind = "json";
  } else if (schema.enum !== undefined) {
    kind = "enum";
  } else if (type === "integer" || type === "number" || type === "boolean" || type === "string") {
    kind = type;
  } else if (type === "object" && schema.properties !== undefined) {
    kind = "object";
  } else if (type === "array" && isScalarItems(schema.items)) {
    kind = "array";
  } else {
    kind = "json";
  }

  return {
    kind,
    schema,
    nullable,
    label: property.title ?? humanize(key),
    description: property.description ?? schema.description ?? null,
    defaultValue: "default" in property ? property.default : schema.default,
    hasDefault: "default" in property || "default" in schema,
    defName: defNameOf(property),
  };
}

function omitAnyOf(property: JsonSchemaProperty): JsonSchemaProperty {
  const { anyOf: _anyOf, ...rest } = property;
  return rest;
}

// A list of plain values gets one input per item; anything else (`items: {}`,
// nested objects) stays a JSON field.
function isScalarItems(items: JsonSchemaProperty | undefined): boolean {
  const type = items?.type;
  return type === "integer" || type === "number" || type === "string" || type === "boolean";
}

/** Filled by another step (see the step's `inputs`); shown, never typed or sent. */
export function isLinkedInput(property: JsonSchemaProperty): boolean {
  return "x-manta-input" in property;
}

/** A fixed value the block always uses; shown, never sent. */
export function isConstant(property: JsonSchemaProperty): boolean {
  return property.const !== undefined;
}

/** The non-null defaults of an object's settings, used when a nullable group is switched on. */
export function seedDefaults(
  properties: Record<string, JsonSchemaProperty>,
  defs: Defs,
): Record<string, unknown> {
  const seeded: Record<string, unknown> = {};

  for (const [key, property] of Object.entries(properties)) {
    if (isLinkedInput(property) || isConstant(property)) {
      continue;
    }

    const resolved = resolveSchema(key, property, defs);

    if (resolved.hasDefault && resolved.defaultValue !== null) {
      seeded[key] = structuredClone(resolved.defaultValue);
    }
  }

  return seeded;
}

export type SchemaGroup = {
  key: string;
  /** Full path from the step's config root, e.g. ["optimize_config", "model_kwargs"]. */
  path: string[];
  resolved: ResolvedSchema;
  property: JsonSchemaProperty;
  properties: Record<string, JsonSchemaProperty>;
  required: string[];
  /** Filled by another step: shown read-only. */
  linked: boolean;
};

/**
 * Every nested group of settings (an object, or a linked def such as DataRecord),
 * depth-first and flattened, so each one can be its own top-level dropdown.
 */
export function collectGroups(
  properties: Record<string, JsonSchemaProperty>,
  defs: Defs,
  path: string[] = [],
): SchemaGroup[] {
  const groups: SchemaGroup[] = [];

  for (const [key, property] of Object.entries(properties)) {
    const resolved = resolveSchema(key, property, defs);
    const linked = isLinkedInput(property);

    if (isConstant(property) || (!linked && resolved.kind !== "object")) {
      continue;
    }

    if (linked && resolved.defName === null) {
      continue;
    }

    const fieldPath = [...path, key];

    groups.push({
      key,
      path: fieldPath,
      resolved,
      property,
      properties: resolved.schema.properties ?? {},
      required: resolved.schema.required ?? [],
      linked,
    });

    if (!linked) {
      groups.push(...collectGroups(resolved.schema.properties ?? {}, defs, fieldPath));
    }
  }

  return groups;
}
