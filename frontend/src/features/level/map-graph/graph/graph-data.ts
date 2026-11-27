// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useShownData } from "../../../project/lib/record-data";
import { serverName, serverQuery } from "../../../project/lib/record-server/client";
import type { LevelQueryScope } from "../../level-sql";
import { levelCtes, scopeKey } from "../../level-sql";
import { baseScope, type BusRow } from "../map-graph-data";

// What the graph reads beyond the map's data: the links inside each
// location (All locations), and what's at one location (the schematic).

export interface InnerLink {
  bus0: string;
  bus1: string;
  carrier: string | null;
}

function loadInnerLinks(scope: LevelQueryScope): Promise<InnerLink[]> {
  return serverQuery<InnerLink>(`
    WITH ${levelCtes(scope)}
    SELECT b.bus0, b.bus1, any_value(b.carrier ORDER BY b.carrier) AS carrier
    FROM ${serverName("manta.branches")} b
    JOIN entities e ON e.entity = b.entity AND e.in_period
    WHERE b.scope = 'within'
    GROUP BY ALL`);
}

/** One row per pair of buses a link joins inside a location, with a carrier. */
export function useInnerLinks(scope: LevelQueryScope | null) {
  const base = scope && baseScope(scope);
  return useShownData("graph-inner-links", base ? [base.period] : null, () =>
    loadInnerLinks(base!),
  );
}

export interface SchematicEntity {
  entity: string;
  ctype: string;
  carrier: string | null;
  bus: string | null;
  bus1: string | null;
  location: string | null;
  location1: string | null;
}

function loadSchematic(scope: LevelQueryScope): Promise<SchematicEntity[]> {
  return serverQuery<SchematicEntity>(`
    WITH ${levelCtes(scope)}
    SELECT entity, ctype, carrier, bus, bus1, location, location1 FROM members ORDER BY ctype, carrier, entity`);
}

/** The active entities at a location: on its buses, or with an end there. */
export function useSchematic(scope: LevelQueryScope | null, location: string | null) {
  const own: LevelQueryScope | null =
    scope && location
      ? {
          level: { kind: "location", location },
          period: scope.period,
          timeWindow: null,
          locations: [],
        }
      : null;
  return useShownData("graph-schematic", own ? [scopeKey(own)] : null, () => loadSchematic(own!));
}

/**
 * The record's bus carriers in display order: the carrier of the buses a
 * location is named after first (AC in PyPSA-Eur), then the rest by how
 * many buses have them.
 */
export function busCarrierOrder(buses: BusRow[]): string[] {
  const count = new Map<string, number>();
  const own = new Map<string, number>();
  for (const bus of buses) {
    const carrier = bus.carrier ?? "";
    count.set(carrier, (count.get(carrier) ?? 0) + 1);
    if (bus.bus === bus.location) own.set(carrier, (own.get(carrier) ?? 0) + 1);
  }
  return [...count.keys()].sort(
    (a, b) =>
      (own.get(b) ?? 0) - (own.get(a) ?? 0) ||
      (count.get(b) ?? 0) - (count.get(a) ?? 0) ||
      a.localeCompare(b),
  );
}
