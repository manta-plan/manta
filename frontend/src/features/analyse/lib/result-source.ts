// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { Aggregate, CustomQuery, QueryResult } from "./custom-query";
import type { ValueKind } from "./result-queries";
import type { InspectFilters } from "./inspect-filters";
import { recordResultSource } from "./record-result-source";

// Where the Analyse page gets result data: the contract between the widgets
// and what answers their queries, which is the record's solved revisions
// (recordResultSource.ts).

/** A query as the widget builder sees it (see resultQueries.ts). */
export interface ResultTableInfo {
  /** The SQL name: FROM supply. */
  name: string;
  label: string;
  description: string;
  /** Unit of `value`. */
  unit: string;
  /** What `value` measures, for axis names: "Supply", "Price". */
  valueLabel: string;
  /** Dimension columns, in the order a query lists them; every query also has `value`. */
  columns: string[];
  kind: ValueKind;
  /** One of ours, rather than the project's. */
  builtIn: boolean;
  /** How a new widget of this query aggregates `value`: amounts add up, prices and rates average. */
  defaultAggregate: Aggregate;
}

/**
 * One result the page can inspect: a solved revision of the project's record
 * ("Base case, myopic"), not a Manta run.
 */
export interface InspectResult {
  /** The revision's name in the record, e.g. `patch/myopic`; what `?result=` holds. */
  id: string;
  label: string;
  /** The scenario it was solved from. */
  scenario: string | null;
  scenarioLabel: string;
  /** The server catalog holding its values, for the real source's queries. */
  catalog: string;
}

/** What there is to analyse: the record's results and periods, and the queries widgets read. */
export interface ResultCatalogue {
  results: InspectResult[];
  periods: string[];
  tables: ResultTableInfo[];
}

export interface QueryRequest {
  query: CustomQuery;
  result: InspectResult;
  /** The page filters the query's placeholders fill in. */
  filters: InspectFilters;
}

export interface ResultSource {
  /** The record's investment periods, from one of its results (every result shares them). */
  loadPeriods(result: InspectResult): Promise<string[]>;
  /** Rejects with an Error whose message the widget shows. */
  runQuery(request: QueryRequest): Promise<QueryResult>;
}

export const resultSource: ResultSource = recordResultSource;
