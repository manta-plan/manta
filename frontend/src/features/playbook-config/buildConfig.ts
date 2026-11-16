import { isConstant, isLinkedInput, resolveSchema } from "../../utils/jsonSchema";
import type { JsonSchemaProperty, PlaybookConfig, PlaybookDetail } from "../../utils/playbookTypes";

type Defs = Record<string, JsonSchemaProperty>;

function prune(
  value: Record<string, unknown>,
  properties: Record<string, JsonSchemaProperty>,
  defs: Defs,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  for (const [key, entry] of Object.entries(value)) {
    const property = properties[key];

    // Blocks declare `additionalProperties: false`: never send an undeclared key.
    if (property === undefined || isLinkedInput(property) || isConstant(property)) {
      continue;
    }

    const { kind, schema } = resolveSchema(key, property, defs);

    result[key] =
      kind === "object" && typeof entry === "object" && entry !== null && !Array.isArray(entry)
        ? prune(entry as Record<string, unknown>, schema.properties ?? {}, defs)
        : entry;
  }

  return result;
}

/** The config to send: every step key kept, but only settings its block declares and a user may set. */
export function buildConfig(playbook: PlaybookDetail, config: PlaybookConfig): PlaybookConfig {
  const result: PlaybookConfig = {};

  for (const [name, value] of Object.entries(config)) {
    const schema = playbook.steps.find((step) => step.name === name)?.block_config_schema;

    // `globals` and steps without a schema pass through as they are.
    result[name] =
      schema === null || schema === undefined
        ? value
        : prune(value, schema.properties ?? {}, schema.$defs ?? {});
  }

  return result;
}
