// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useShownData, type ShownData } from "../../project/lib/record-data";
import { serverQuery } from "../../project/lib/record-server/client";
import { scopeKey, type LevelQueryScope } from "../level-sql";
import {
  inputParts,
  inputsSql,
  resultParts,
  resultsSql,
  type InputParts,
  type ResultParts,
} from "./tile-sql";

// What the tiles read: one query of the inputs at every level and, on
// Inspect, one of the run result at a type, carrier or entity level. Both
// are a single row; its nested parts come as JSON text.

export interface Hours {
  /** Weighted hours in the time window. */
  span_hours: number;
  /** Weighted hours in the whole period (a year). */
  period_hours: number;
}

export interface Counts {
  active: number;
  not_active: number;
  existing: number;
  candidate: number;
  /** Active entities with an asset_status (none when the record has no such column). */
  with_status: number;
}

/** The active members of one type and carrier. Capacities in MW, MWh or MVA. */
export interface Group {
  ctype: string;
  carrier: string | null;
  color: string | null;
  name: string | null;
  entities: number;
  existing: number;
  candidate: number;
  capacity: number | null;
  /** Optimised where the run has it, else the starting capacity. */
  actual: number | null;
  new_build: number | null;
  largest: string | null;
  largest_capacity: number | null;
  largest_actual: string | null;
  largest_actual_capacity: number | null;
}

export interface Volumes {
  stores: number;
  /** MWh. */
  storage: number | null;
  storage_actual: number | null;
  lines: number;
  /** MVA·km. */
  transmission: number | null;
  transmission_actual: number | null;
  lines_without_length: number;
  kv: number[] | null;
  unit_efficiency: number | null;
}

export interface EntityRow {
  entity: string;
  ctype: string;
  carrier: string | null;
  name: string | null;
  color: string | null;
  bus: string | null;
  location: string | null;
  location1: string | null;
  cap_attribute: string | null;
  capacity: number | null;
  capacity_opt: number | null;
  status: string | null;
  max_hours: number | null;
  length: number | null;
}

/** The summed p_set over the window: MW, weighted mean. */
export interface LoadStats {
  loads: number;
  peak: number | null;
  mean: number | null;
  largest: string | null;
  largest_mean: number | null;
  largest_peak: number | null;
}

export interface CapacityFactorEstimate {
  estimate: number | null;
  with_profile: number;
  generators: number;
}

export interface StoreEfficiency {
  charge: number | null;
  discharge: number | null;
}

export interface LocationsInfo {
  count: number;
  buses: { carrier: string | null; buses: number }[];
  regions: { level: string; zones: number } | null;
}

export interface TileInputs {
  hours: Hours;
  counts: Counts;
  groups: Group[];
  volumes: Volumes | null;
  entity: EntityRow | null;
  load: LoadStats | null;
  capacityFactor: CapacityFactorEstimate | null;
  storeEfficiency: StoreEfficiency | null;
  locations: LocationsInfo | null;
}

/** One type's flow at its members' first bus over the window, MWh (weighted). */
export interface Flow {
  ctype: string;
  net: number;
  out: number;
  in: number;
  both_ways: number;
}

export interface GeneratorResults {
  generation: number | null;
  available: number | null;
  curtailed: number | null;
  market_value: number | null;
  mean_price: number | null;
}

export interface TileResults {
  hours: Hours;
  flows: Flow[];
  generators: GeneratorResults | null;
  /** Stores' state of charge summed over the window's weighted hours, MWh·h. */
  stores: { energy: number | null } | null;
}

const parse = <T>(text: unknown): T | null =>
  typeof text === "string" ? (JSON.parse(text) as T) : null;

type InputsRow = Record<
  | "hours"
  | "counts"
  | "groups"
  | "volumes"
  | "entity"
  | "load"
  | "capacity_factor"
  | "store_efficiency"
  | "buses"
  | "regions",
  string | null
> & {
  location_count?: number | null;
};

async function loadInputs(scope: LevelQueryScope, parts: InputParts): Promise<TileInputs> {
  const [row] = await serverQuery<InputsRow>(inputsSql(scope, parts));
  return {
    hours: parse<Hours>(row.hours) ?? { span_hours: 0, period_hours: 0 },
    counts: parse<Counts>(row.counts) ?? {
      active: 0,
      not_active: 0,
      existing: 0,
      candidate: 0,
      with_status: 0,
    },
    groups: parse<Group[]>(row.groups) ?? [],
    volumes: parts.volumes || parts.entity ? parse<Volumes>(row.volumes) : null,
    entity: parts.entity ? parse<EntityRow>(row.entity) : null,
    load: parts.load ? parse<LoadStats>(row.load) : null,
    capacityFactor: parts.capacityFactor
      ? parse<CapacityFactorEstimate>(row.capacity_factor)
      : null,
    storeEfficiency: parts.storeEfficiency ? parse<StoreEfficiency>(row.store_efficiency) : null,
    locations: parts.locations
      ? {
          count: Number(row.location_count ?? 0),
          buses: parse<LocationsInfo["buses"]>(row.buses) ?? [],
          regions: parse<LocationsInfo["regions"]>(row.regions),
        }
      : null,
  };
}

async function loadResults(scope: LevelQueryScope, parts: ResultParts): Promise<TileResults> {
  const [row] = await serverQuery<
    Record<"hours" | "flows" | "generators" | "stores", string | null>
  >(resultsSql(scope, parts));
  return {
    hours: parse<Hours>(row.hours) ?? { span_hours: 0, period_hours: 0 },
    flows: parse<Flow[]>(row.flows) ?? [],
    generators: parts.generators ? parse<GeneratorResults>(row.generators) : null,
    stores: parts.stores ? parse<{ energy: number | null }>(row.stores) : null,
  };
}

export function useTileInputs(
  scope: LevelQueryScope | null,
  results: boolean,
): ShownData<TileInputs> {
  const parts = scope ? inputParts(scope.level, results) : null;
  return useShownData(
    "level-tiles-inputs",
    scope && parts ? [scopeKey(scope), JSON.stringify(parts)] : null,
    () => loadInputs(scope!, parts!),
  );
}

/** The run result's figures; skipped (null args) on Build and at levels without result tiles. */
export function useTileResults(
  scope: LevelQueryScope | null,
  results: boolean,
): ShownData<TileResults> | null {
  const parts = scope && results ? resultParts(scope.level) : null;
  const data = useShownData(
    "level-tiles-results",
    scope && parts ? [scopeKey(scope), JSON.stringify(parts)] : null,
    () => loadResults(scope!, parts!),
  );
  return parts ? data : null;
}
