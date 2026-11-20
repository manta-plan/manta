// A scenario is a set of mutations/patches against the base model — the
// same concept as a database migration: an ordered set of changes applied
// on top of a base schema, rather than a full standalone copy of it.
//
// A mutation is either a direct edit (an explicit, one-off change) or a
// rule (a transformation applied across a filtered set of underlying rows,
// e.g. "2x capacity where carrier = coal") — the same distinction PLEXOS
// draws between editing a property outright and applying a scenario
// multiplier/adjustment to it.

export type ScenarioMutationOp = "add" | "modify" | "remove";
export type ScenarioMutationKind = "direct" | "rule";
export type ScenarioModelResolution = "zonal" | "nodal";
export type ScenarioRuleOperation = "set" | "add" | "multiply" | "min" | "max";

export interface ScenarioRule {
  filterField: string;
  filterValue: string;
  property: string;
  operation: ScenarioRuleOperation;
  value: string;
}

export interface ScenarioDirectChange {
  property: string;
  previousValue: string;
  value: string;
}

export interface ScenarioMutation {
  id: string;
  name: string;
  targetId: string; // ModelNode id this mutation patches
  op: ScenarioMutationOp;
  kind: ScenarioMutationKind;
  description: string;
  rule?: ScenarioRule;
  direct?: ScenarioDirectChange;
}

export interface Scenario {
  id: string;
  name: string;
  modelResolution: ScenarioModelResolution;
  baseScenarioId?: string;
  baseModelSourceIds?: string[];
  // Pins the zone count a zonal-resolution scenario's live clustering uses
  // (see src/lib/clustering/zonalClustering.ts) — absent means the default
  // zone count. Only meaningful when modelResolution === 'zonal'.
  zoningParams?: { zoneCount: number };
  mutations: ScenarioMutation[];
}

export const INITIAL_SCENARIOS: Scenario[] = [
  {
    id: "scenario-base",
    name: "Base Scenario",
    modelResolution: "nodal",
    mutations: [],
  },
];
