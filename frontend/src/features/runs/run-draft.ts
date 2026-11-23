// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { isStepActive } from "../playbook-config/conditions";
import { validateStep, type FieldError } from "../playbook-config/validation";
import { humanize } from "../../utils/jsonSchema";
import type { PlaybookConfig, PlaybookDetail, PlaybookStep } from "../../utils/playbookTypes";

/** The steps that will run for this config, in step order. */
export function getActiveSteps(detail: PlaybookDetail, config: PlaybookConfig): PlaybookStep[] {
  return detail.steps.filter((step) => isStepActive(step, config));
}

/** Ajv errors of the active steps, by step name. A step without errors has no entry. */
export function getStepErrors(
  detail: PlaybookDetail,
  config: PlaybookConfig,
): Map<string, FieldError[]> {
  const byStep = new Map<string, FieldError[]>();

  for (const step of getActiveSteps(detail, config)) {
    const found = validateStep(step, config[step.name] ?? {});

    if (found.length > 0) {
      byStep.set(step.name, found);
    }
  }

  return byStep;
}

/** What blocks Start, or null when the settings pass the local check. */
export function describeStepErrors(errors: Map<string, FieldError[]>): string | null {
  return errors.size === 0
    ? null
    : `Resolve the settings of ${[...errors.keys()].map(humanize).join(", ")} before starting the run.`;
}

/** The message the backend or the network gave, with a capital; or the fallback when it has none. */
export function toMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message !== ""
    ? error.message.charAt(0).toUpperCase() + error.message.slice(1)
    : fallback;
}

/** Why the Runs panel has no rows, or null when it has some. */
export function getRunsPanelEmptyMessage(options: {
  hasRows: boolean;
  isFiltered: boolean;
}): string | null {
  if (options.hasRows) {
    return null;
  }

  return options.isFiltered
    ? "No runs match the current filters."
    : "No runs yet — create one to get started.";
}
