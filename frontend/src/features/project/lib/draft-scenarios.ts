// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import type { EntityAttribute, Revision } from "./record-server/types";
import { serverName, serverQuery, sqlString } from "./record-server/client";

// Draft scenarios: made on the Build tab, kept in the browser per project
// until the backend can write them into the record as layers. A draft starts
// from one of the record's scenarios (its parent) and lists changes to its
// inputs, applied in order: an attribute changed (`set` on an attribute, for
// one entity or those matching some properties, in the vocabulary of
// datarecord's editing API) or a new entity. See `toChangeSet` for what the
// backend is handed.

export type DraftChangeOp = "set" | "multiply" | "add";

/** One entity, or every entity of a ctype matching a carrier and a location (either optional). */
export type DraftChangeTarget =
  | {
      kind: "entity";
      entity: string;
      ctype: string;
      carrier: string | null;
      location: string | null;
    }
  | { kind: "filter"; ctype: string; carrier: string | null; location: string | null };

export interface DraftAttributeChange {
  id: string;
  kind: "attribute";
  /** An entity attribute (one without a bus): p_nom, capital_cost, p_max_pu, … */
  attribute: string;
  target: DraftChangeTarget;
  op: DraftChangeOp;
  value: number;
}

/** A new entity: its ctype and carrier, the bus at each of its connections (by role), and the values it's given (the rest take the manifest's defaults). */
export interface DraftNewEntity {
  id: string;
  kind: "new-entity";
  entity: string;
  ctype: string;
  carrier: string | null;
  buses: Record<string, string>;
  values: Record<string, number>;
}

export type DraftChange = DraftAttributeChange | DraftNewEntity;

/** A change as it's saved: its id is made for a new one. */
export type DraftChangeInput = DraftChange extends infer C
  ? C extends DraftChange
    ? Omit<C, "id"> & { id?: string }
    : never
  : never;

export interface DraftScenario {
  id: string;
  /** The record it belongs to, and the revision (a scenario's name) it starts from. */
  recordId: string;
  parent: string;
  name: string;
  description: string;
  changes: DraftChange[];
  createdAt: string;
  updatedAt: string;
}

// ------------------------------------------------------------------ Hand-off

/**
 * What the backend is handed to make a draft a scenario: a new layer whose
 * parent is `parent`, applying `changes` in order. `where` holds the entity,
 * or the properties an entity must match (all of them); `op` is applied to
 * the parent's value (a time series value by value).
 */
export type ScenarioChangeSetItem =
  | {
      attribute: string;
      where: { entity: string } | { ctype: string; carrier?: string; location?: string };
      op: DraftChangeOp;
      value: number;
    }
  | {
      op: "create";
      entity: string;
      properties: { ctype: string; carrier?: string };
      connections: { role: string; bus: string }[];
      values: Record<string, number>;
    };

export interface ScenarioChangeSet {
  version: 1;
  record: string;
  parent: string;
  name: string;
  description: string;
  changes: ScenarioChangeSetItem[];
}

export function toChangeSet(draft: DraftScenario): ScenarioChangeSet {
  return {
    version: 1,
    record: draft.recordId,
    parent: draft.parent,
    name: draft.name,
    description: draft.description,
    changes: draft.changes.map((change): ScenarioChangeSetItem => {
      if (change.kind === "new-entity") {
        return {
          op: "create",
          entity: change.entity,
          properties: {
            ctype: change.ctype,
            ...(change.carrier ? { carrier: change.carrier } : {}),
          },
          connections: Object.entries(change.buses).map(([role, bus]) => ({ role, bus })),
          values: change.values,
        };
      }
      const { attribute, target, op, value } = change;
      return {
        attribute,
        where:
          target.kind === "entity"
            ? { entity: target.entity }
            : {
                ctype: target.ctype,
                ...(target.carrier ? { carrier: target.carrier } : {}),
                ...(target.location ? { location: target.location } : {}),
              },
        op,
        value,
      };
    }),
  };
}

// ------------------------------------------------------------------ Matching

/** What a change is matched against: an entity, with where it is. */
export interface DraftSubject {
  entity: string;
  ctype: string;
  carrier: string | null;
  locations: string[];
}

export function targetMatches(target: DraftChangeTarget, subject: DraftSubject): boolean {
  if (target.kind === "entity") return target.entity === subject.entity;
  return (
    target.ctype === subject.ctype &&
    (target.carrier === null || target.carrier === subject.carrier) &&
    (target.location === null || subject.locations.includes(target.location))
  );
}

/** A constant value after the changes; null where it can't be told (no value before, or none set). */
export function applyChanges(
  before: number | null,
  changes: Pick<DraftAttributeChange, "op" | "value">[],
): number | null {
  let value = before;
  for (const change of changes) {
    if (change.op === "set") value = change.value;
    else if (value === null) return null;
    else value = change.op === "multiply" ? value * change.value : value + change.value;
  }
  return value;
}

/** An attribute's constant value, as a number; null for a series or a non-number. */
export function numericValue(
  attribute: Pick<EntityAttribute, "value" | "seriesRows"> | undefined,
): number | null {
  if (!attribute || attribute.seriesRows > 0 || attribute.value === null) return null;
  const number = Number(attribute.value);
  return Number.isFinite(number) ? number : null;
}

// ------------------------------------------------------------------ Wording

export function describeOp(op: DraftChangeOp, value: number, unit?: string): string {
  const number = value.toLocaleString(undefined, { maximumFractionDigits: 6 });
  if (op === "multiply") return `× ${number}`;
  const suffix = unit ? ` ${unit}` : "";
  return op === "set"
    ? `= ${number}${suffix}`
    : `${value < 0 ? "−" : "+"} ${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 6 })}${suffix}`;
}

/** "Generator · offwind-dc · at BE0 1AC": what a new entity is and where. */
export function describeNewEntity(
  change: DraftNewEntity,
  carrierLabel: (carrier: string) => string = (carrier) => carrier,
  busLocation: (bus: string) => string = (bus) => bus,
): string {
  const at = [...new Set(Object.values(change.buses).map(busLocation))];
  return [
    change.ctype,
    change.carrier && carrierLabel(change.carrier),
    at.length > 0 && `at ${at.join(" → ")}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

// ------------------------------------------------------------------ Storage

const STORAGE_KEY = "manta-draft-scenarios-v1";

function stored(): Record<string, DraftScenario[]> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Record<string, DraftScenario[]>;
  } catch {
    return {};
  }
}

export function loadProjectDrafts(projectId: string): DraftScenario[] {
  // Drafts saved before new entities had attribute changes without a kind.
  return (stored()[projectId] ?? []).map((draft) => ({
    ...draft,
    changes: draft.changes.map((change) =>
      change.kind
        ? change
        : { ...(change as Omit<DraftAttributeChange, "kind">), kind: "attribute" as const },
    ),
  }));
}

export function saveProjectDrafts(projectId: string | null, drafts: DraftScenario[]) {
  if (!projectId) return;
  try {
    const all = stored();
    all[projectId] = drafts;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Storage full or blocked: the drafts last until the page reloads.
  }
}

// ------------------------------------------------------------------ Server reads

/** Attributes some entity of the ctype stores in the shown scenario: the ones worth offering to change. */
export async function loadCtypeAttributes(ctype: string): Promise<string[]> {
  const rows = await serverQuery<{ attribute: string }>(
    `SELECT attribute FROM ${serverName("manta.ctype_attributes")} WHERE ctype = ${sqlString(ctype)} ORDER BY attribute`,
  );
  return rows.map((row) => row.attribute);
}

/** Whether a change can act on the attribute: a number per entity (not per connection, not a label). */
export function isChangeable(
  spec: { dims: string[]; dtype?: string; one_of?: string } | undefined,
): boolean {
  return Boolean(
    spec &&
    spec.dims.includes("entity") &&
    !spec.dims.includes("connection") &&
    !spec.one_of &&
    (!spec.dtype || /float|int|double|number/i.test(spec.dtype)),
  );
}

/** Whether an entity of this name is in the shown scenario already. */
export async function entityExists(entity: string): Promise<boolean> {
  const rows = await serverQuery<{ n: number }>(
    `SELECT count(*)::INT AS n FROM ${serverName("properties.entity")} WHERE entity = ${sqlString(entity)}`,
  );
  return (rows[0]?.n ?? 0) > 0;
}

/** How entities of a ctype (and carrier) connect: each role, with the bus carriers they connect to there, most used first. */
export async function loadCtypeConnections(
  ctype: string,
  carrier: string | null,
): Promise<{ role: string; busCarriers: string[] }[]> {
  const rows = await serverQuery<{ role: string; busCarrier: string | null; n: number }>(`
    SELECT c.role, b.carrier AS "busCarrier", count(*)::INT AS n
    FROM ${serverName("properties.connection")} c
    JOIN ${serverName("properties.entity")} e ON e.entity = c.connection.entity
    JOIN ${serverName("manta.bus_location")} b ON b.bus = c.connection.bus
    WHERE e.ctype = ${sqlString(ctype)}${carrier ? ` AND e.carrier = ${sqlString(carrier)}` : ""}
    GROUP BY ALL ORDER BY c.role, n DESC`);
  const roles = new Map<string, string[]>();
  for (const row of rows) {
    const carriers = roles.get(row.role) ?? [];
    if (row.busCarrier) carriers.push(row.busCarrier);
    roles.set(row.role, carriers);
  }
  return [...roles].map(([role, busCarriers]) => ({ role, busCarriers }));
}

/** Every bus, with where it is and what it carries. */
export async function loadBuses(): Promise<
  { bus: string; location: string; carrier: string | null }[]
> {
  return serverQuery(
    `SELECT bus, location, carrier FROM ${serverName("manta.bus_location")} ORDER BY location, bus`,
  );
}

/**
 * The Scenario field of the change and entity dialogs. Per saved scenario of
 * the record: a read-only line (but for the base, which starts the list), then
 * a new draft built on it; after them, the record's drafts. Only what's built
 * on the scenario shown can be picked (and the draft a change is in, when
 * editing): a change's preview is worked out on the scenario shown, so the
 * rest waits until their scenario is shown, which the hint says.
 */
export function draftScenarioOptions(
  drafts: DraftScenario[],
  {
    recordId,
    revisions,
    shown,
    keepId,
    newValue,
  }: {
    recordId: string;
    revisions: Revision[];
    shown: string | null;
    keepId?: string;
    newValue: string;
  },
): {
  usable: DraftScenario[];
  options: { value: string; label: string; disabled?: boolean }[];
  hint?: string;
} {
  const labelOf = (name: string) =>
    revisions.find((revision) => revision.name === name)?.label ?? name;
  const ofRecord = drafts.filter((draft) => draft.recordId === recordId);
  const usable = ofRecord.filter((draft) => draft.parent === shown || draft.id === keepId);
  const options: { value: string; label: string; disabled?: boolean }[] = [];
  for (const scenario of revisions.filter((revision) => revision.kind === "scenario")) {
    if (scenario.parent)
      options.push({
        value: `saved:${scenario.name}`,
        label: `${scenario.label} · saved in the record, read-only`,
        disabled: true,
      });
    options.push(
      scenario.name === shown
        ? { value: newValue, label: `New scenario from ${scenario.label}` }
        : {
            value: `${newValue}:${scenario.name}`,
            label: `New scenario from ${scenario.label}`,
            disabled: true,
          },
    );
  }
  for (const draft of ofRecord) {
    options.push(
      usable.includes(draft)
        ? { value: draft.id, label: draft.name }
        : {
            value: draft.id,
            label: `${draft.name} · built on ${labelOf(draft.parent)}`,
            disabled: true,
          },
    );
  }
  const waiting = options.some((option) => option.disabled && !option.value.startsWith("saved:"));
  return {
    usable,
    options,
    hint: waiting
      ? "Greyed-out options are built on another scenario: show that scenario first to use them."
      : undefined,
  };
}

// ------------------------------------------------------------------ Dialog seeds

/** What the Change dialog opens with: a draft to add to (else it asks), a change to edit, or what to prefill. */
export interface ChangeDialogSeed {
  draftId?: string;
  change?: DraftAttributeChange;
  target?: DraftChangeTarget;
  attribute?: string;
}

/** What the New entity dialog opens with: a draft to add to (else it asks), a new entity to edit, or what to prefill. */
export interface EntityDialogSeed {
  draftId?: string;
  change?: DraftNewEntity;
  ctype?: string;
  carrier?: string | null;
  location?: string;
}
