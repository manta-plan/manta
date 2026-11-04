import Ajv, { type ErrorObject, type ValidateFunction } from "ajv";
import type { BlockConfigSchema, PlaybookStep } from "../../utils/playbookTypes";
import { exactlyOneErrors, exactlyOneOf } from "./exclusiveSettings";

const ajv = new Ajv({ allErrors: true, strict: false });
ajv.addKeyword("x-manta-input");

const compiled = new WeakMap<BlockConfigSchema, ValidateFunction>();

// A setting another step fills in is wired by the backend, so the user can't be
// asked to supply it.
function withoutLinkedRequirements(schema: BlockConfigSchema): BlockConfigSchema {
  const linked = new Set(
    Object.entries(schema.properties ?? {})
      .filter(([, property]) => "x-manta-input" in property)
      .map(([key]) => key),
  );

  return { ...schema, required: (schema.required ?? []).filter((key) => !linked.has(key)) };
}

function validatorFor(schema: BlockConfigSchema): ValidateFunction {
  let validate = compiled.get(schema);

  if (validate === undefined) {
    validate = ajv.compile(withoutLinkedRequirements(schema));
    compiled.set(schema, validate);
  }

  return validate;
}

export type FieldError = {
  /** Slash path inside the step's config, e.g. "optimize_config/model_kwargs/chunk". */
  path: string;
  message: string;
};

function toFieldError(error: ErrorObject): FieldError {
  const params = error.params as { missingProperty?: string; additionalProperty?: string };
  const child = params.missingProperty ?? params.additionalProperty;
  const path = child === undefined ? error.instancePath : `${error.instancePath}/${child}`;

  return { path: path.replace(/^\//, ""), message: error.message ?? "Invalid value" };
}

/** Errors in one step's settings; [] when it is valid or has no schema. */
export function validateStep(step: PlaybookStep, value: unknown): FieldError[] {
  if (step.block_config_schema === null) {
    return [];
  }

  const validate = validatorFor(step.block_config_schema);
  const schemaErrors = validate(value) ? [] : (validate.errors ?? []).map(toFieldError);
  const groups = step.block === null ? undefined : exactlyOneOf[step.block];

  if (groups === undefined || typeof value !== "object" || value === null) {
    return schemaErrors;
  }

  return [...schemaErrors, ...exactlyOneErrors(groups, value as Record<string, unknown>)];
}
