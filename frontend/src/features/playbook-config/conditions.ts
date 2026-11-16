import type { PlaybookConfig, PlaybookDetail, PlaybookStep } from "../../utils/playbookTypes";

export function getIn(value: unknown, path: string[]): unknown {
  return path.reduce<unknown>(
    (current, key) =>
      typeof current === "object" && current !== null
        ? (current as Record<string, unknown>)[key]
        : undefined,
    value,
  );
}

/** A step with a `when` only runs when that setting has the given value. */
export function isStepActive(step: PlaybookStep, config: PlaybookConfig): boolean {
  return step.when === null || getIn(config, step.when.config.split(".")) === step.when.equals;
}

export type GlobalField = {
  /** Dotted config path, e.g. "globals.expansion_mode". */
  path: string;
  options: unknown[];
};

/**
 * `globals` has no schema: its settings only exist as `when` clauses. So each
 * distinct `when.config` becomes a select whose options are the distinct `equals`.
 */
export function deriveGlobalFields(playbook: Pick<PlaybookDetail, "steps">): GlobalField[] {
  const fields = new Map<string, unknown[]>();

  for (const step of playbook.steps) {
    if (step.when === null) {
      continue;
    }

    const options = fields.get(step.when.config) ?? [];

    if (!options.includes(step.when.equals)) {
      options.push(step.when.equals);
    }

    fields.set(step.when.config, options);
  }

  return [...fields].map(([path, options]) => ({ path, options }));
}

/** A step input like `${steps.expansion_overnight.output}` -> the step and field it comes from. */
export function linkedSource(
  step: Pick<PlaybookStep, "inputs">,
  key: string,
): { stepName: string; field: string } | null {
  const match = /^\$\{steps\.([^.}]+)\.([^}]+)\}$/.exec(step.inputs[key] ?? "");

  return match === null ? null : { stepName: match[1], field: match[2] };
}

/** Sets a dotted path ("globals.expansion_mode") without mutating the config. */
export function setAtPath(config: PlaybookConfig, path: string, value: unknown): PlaybookConfig {
  const [head, ...rest] = path.split(".");

  if (rest.length === 0) {
    return { ...config, [head]: value as Record<string, unknown> };
  }

  return { ...config, [head]: setNested(config[head] ?? {}, rest, value) };
}

function setNested(
  object: Record<string, unknown>,
  path: string[],
  value: unknown,
): Record<string, unknown> {
  const [head, ...rest] = path;
  const child = object[head];

  return {
    ...object,
    [head]:
      rest.length === 0
        ? value
        : setNested(
            typeof child === "object" && child !== null ? (child as Record<string, unknown>) : {},
            rest,
            value,
          ),
  };
}
