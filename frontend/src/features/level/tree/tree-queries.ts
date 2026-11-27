// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { serverName, serverQuery, sqlString } from "../../project/lib/record-server/client";
import { entitiesSql } from "../level-sql";

// The record tree's reads (the SQL tab's "Record tree"): every count and list
// is of entities active in the investment period, from the shared
// `entities` fragment, in the shown catalog.

/** A node lists at most this many entities, then "n more in the table". */
export const LEAF_CAP = 80;
/** Search lists at most this many entities, and locations. */
export const SEARCH_ENTITIES = 40;
export const SEARCH_LOCATIONS = 20;

const withEntities = (period: string) => `WITH entities AS (${entitiesSql(period)})`;

export function contains(column: string, term: string): string {
  const words = term.trim().split(/\s+/).filter(Boolean);
  return (
    words
      .map(
        (word) =>
          `${column} ILIKE ${sqlString(`%${word.replace(/[\\%_]/g, (c) => `\\${c}`)}%`)} ESCAPE '\\'`,
      )
      .join(" AND ") || "false"
  );
}

export interface TreeCount {
  ctype: string;
  carrier: string | null;
  entities: number;
}

/** Active entities per component type and carrier. */
export function treeCounts(period: string): Promise<TreeCount[]> {
  return serverQuery<TreeCount>(`${withEntities(period)}
    SELECT ctype, carrier, count(*)::INTEGER AS entities
    FROM entities WHERE in_period
    GROUP BY ALL ORDER BY ctype, carrier NULLS FIRST`);
}

export interface TreeLocation {
  location: string;
  entities: number;
}

/** Every real location, with its active entities (a two-ended entity counts at both ends). */
export function treeLocations(period: string): Promise<TreeLocation[]> {
  return serverQuery<TreeLocation>(`${withEntities(period)}
    SELECT l.location, count(DISTINCT e.entity)::INTEGER AS entities
    FROM ${serverName("manta.locations")} l
    LEFT JOIN entities e ON e.in_period AND list_contains(e.locations, l.location)
    GROUP BY ALL ORDER BY l.location`);
}

export interface TreeBus {
  bus: string;
  carrier: string | null;
  entities: number;
}

/** The buses at one location (as data: the AC bus, the H2 bus, …), with their active entities. */
export function treeBuses(period: string, location: string): Promise<TreeBus[]> {
  return serverQuery<TreeBus>(`${withEntities(period)}
    SELECT b.bus, b.carrier, count(DISTINCT e.entity)::INTEGER AS entities
    FROM ${serverName("manta.bus_location")} b
    LEFT JOIN entities e ON e.in_period AND list_contains(e.buses, b.bus)
    WHERE b.location = ${sqlString(location)}
    GROUP BY ALL ORDER BY b.bus`);
}

export interface TreeLeaf {
  entity: string;
  ctype: string;
  carrier: string | null;
  location: string | null;
  /** Every active entity in the node, not only the ones listed. */
  total: number;
}

/** Which entities a node lists: a type (any carrier, or one; null is "no carrier"), or a bus. */
export type LeafFilter =
  | { kind: "type"; ctype: string; carrier?: string | null }
  | { kind: "bus"; bus: string };

/** The first LEAF_CAP active entities of a node, with the node's total. */
export function treeLeaves(period: string, filter: LeafFilter): Promise<TreeLeaf[]> {
  const condition =
    filter.kind === "bus"
      ? `list_contains(buses, ${sqlString(filter.bus)})`
      : `ctype = ${sqlString(filter.ctype)}` +
        (filter.carrier === undefined
          ? ""
          : filter.carrier === null
            ? " AND carrier IS NULL"
            : ` AND carrier = ${sqlString(filter.carrier)}`);
  return serverQuery<TreeLeaf>(`${withEntities(period)}
    SELECT entity, ctype, carrier, location, (count(*) OVER ())::INTEGER AS total
    FROM entities WHERE in_period AND ${condition}
    ORDER BY entity LIMIT ${LEAF_CAP}`);
}

export interface EntityHit {
  entity: string;
  ctype: string;
  carrier: string | null;
  location: string | null;
}

/** Active entities whose id holds every word of the term: one more than SEARCH_ENTITIES, to tell there are more. */
export function searchEntities(period: string, term: string): Promise<EntityHit[]> {
  return serverQuery<EntityHit>(`${withEntities(period)}
    SELECT entity, ctype, carrier, location
    FROM entities WHERE in_period AND ${contains("entity", term)}
    ORDER BY entity LIMIT ${SEARCH_ENTITIES + 1}`);
}
