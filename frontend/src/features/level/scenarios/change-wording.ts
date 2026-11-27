// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { DraftChangeOp, DraftChangeTarget } from "../../project/lib/draft-scenarios";

// How a draft change reads in the Scenarios panel and the change dialog's
// preview: "multiply by 1.3", "Generator Solar at BE0 1AC".

export const formatValue = (value: number) =>
  value.toLocaleString(undefined, { maximumFractionDigits: 4 });

/** "multiply by 1.3", "add −2 MW", "set to 5 MW". */
export function opWords(op: DraftChangeOp, value: number, unit?: string | null): string {
  const suffix = unit ? ` ${unit}` : "";
  if (op === "multiply") return `multiply by ${formatValue(value)}`;
  if (op === "add") return `add ${formatValue(value)}${suffix}`;
  return `set to ${formatValue(value)}${suffix}`;
}

/** "Generator Solar at BE0 1AC", "Generator" (any carrier, anywhere). */
export function filterWords(
  target: Extract<DraftChangeTarget, { kind: "filter" }>,
  carrierLabel: (carrier: string) => string,
): string {
  return [
    target.ctype,
    target.carrier && carrierLabel(target.carrier),
    target.location && `at ${target.location}`,
  ]
    .filter(Boolean)
    .join(" ");
}

export const plural = (count: number, one: string, many: string) =>
  `${count.toLocaleString()} ${count === 1 ? one : many}`;
