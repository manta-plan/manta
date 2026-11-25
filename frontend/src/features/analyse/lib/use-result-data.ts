import { createContext, useContext, useMemo } from "react";
import useSWRImmutable from "swr/immutable";
import { isPlaceholderCondition, type CustomQuery, type QueryResult } from "./custom-query";
import { useInspectFilters, type InspectFilters } from "./inspect-filters";
import {
  resultSource,
  type InspectResult,
  type QueryRequest,
  type ResultCatalogue,
} from "./result-source";
import { loadColumnValues, queryTableInfo } from "./record-result-source";
import { BUILT_IN_QUERIES } from "./result-queries";
import { recordResults } from "../../project/lib/record-results";
import { useProjectStore } from "../../project/store/project-store";

// How the Analyse tab reads result data: through SWR, in the app's one record
// cache (recordData.ts), like Build and Inspect. A solved result never
// changes, so whatever is read from its catalog is cached for good, keyed by
// that catalog: a duplicate widget, a built-in and its copy, going back to a
// page or flipping back to an earlier filter ask the server nothing.

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Something read from one result's catalog, cached for good. `key` names it
 * (the catalog first); null skips. With `keepPrevious`, the last key's data
 * stays while the next loads.
 */
export function useResultRead<T>(
  name: string,
  key: readonly unknown[] | null,
  load: () => Promise<T>,
  keepPrevious = false,
) {
  return useSWRImmutable(
    key === null ? null : ["result", `analyse-${name}`, ...key],
    () => load(),
    { shouldRetryOnError: false, keepPreviousData: keepPrevious },
  );
}

// ------------------------------------------------------------ Catalogue

export type CatalogueState =
  | { status: "loading" }
  | { status: "error"; error: string; retry: () => void }
  | { status: "ready"; catalogue: ResultCatalogue };

const NO_PERIODS: string[] = [];
const TABLES = BUILT_IN_QUERIES.map(queryTableInfo);

/**
 * The catalogue: the results of the project's record (loaded for the whole
 * project, see recordSlice), its investment periods, and the computed tables
 * widgets read. The page calls this once and provides it below.
 */
export function useLoadResultCatalogue(): CatalogueState {
  const recordInfo = useProjectStore((s) => s.record?.info ?? null);
  const recordStatus = useProjectStore((s) => s.recordStatus);
  const recordError = useProjectStore((s) => s.recordError);
  const reconnect = useProjectStore((s) => s.reconnect);
  const results = useMemo(() => (recordInfo ? recordResults(recordInfo) : null), [recordInfo]);
  // Every result has the same periods; the first one's are read.
  const first = results?.[0] ?? null;
  const periodsRead = useResultRead("periods", first ? [first.catalog] : null, () =>
    resultSource.loadPeriods(first!),
  );
  // A record without results has nothing to read periods from, and nothing to show.
  const periods = first ? periodsRead.data : NO_PERIODS;
  const catalogue = useMemo(
    () => (results && periods ? { results, periods, tables: TABLES } : null),
    [results, periods],
  );
  if (periodsRead.error !== undefined && !periodsRead.data)
    return {
      status: "error",
      error: errorMessage(periodsRead.error),
      retry: () => void periodsRead.mutate(),
    };
  if (recordStatus === "error")
    return {
      status: "error",
      error: recordError ?? "Can't reach the record server.",
      retry: reconnect,
    };
  if (catalogue) return { status: "ready", catalogue };
  return { status: "loading" };
}

export const ResultCatalogueContext = createContext<ResultCatalogue | null>(null);

/** The loaded catalogue; only for components inside the Analyse page. */
export function useResultCatalogue(): ResultCatalogue {
  const catalogue = useContext(ResultCatalogueContext);
  if (!catalogue) throw new Error("useResultCatalogue needs a ResultCatalogueContext provider");
  return catalogue;
}

/** A result of the catalogue by id, if there is one. */
function useCatalogueResult(resultId: string | null): InspectResult | null {
  const catalogue = useContext(ResultCatalogueContext);
  return catalogue?.results.find((item) => item.id === resultId) ?? null;
}

// ------------------------------------------------------------ Widget queries

/** How far a widget's data has got; a QueryState is one. */
export type LoadState =
  | { status: "loading" }
  | { status: "error"; error: string; retry: () => void }
  | { status: "ready"; isRefreshing: boolean };

export type QueryState =
  | { status: "loading" }
  | { status: "error"; error: string; retry: () => void }
  /** `isRefreshing`: these are the previous answer's values while a new one loads. */
  | { status: "ready"; data: QueryResult; isRefreshing: boolean };

/** Only the filters the query's placeholders read, so other filter changes don't re-ask. */
function followedFilters(request: QueryRequest): Partial<InspectFilters> {
  const placeholders = new Set(
    request.query.where.filter(isPlaceholderCondition).map((condition) => condition.placeholder),
  );
  return {
    ...(placeholders.has("buses") ? { buses: request.filters.buses } : {}),
    ...(placeholders.has("period") ? { period: request.filters.period } : {}),
    ...(placeholders.has("carriers") ? { carriers: request.filters.carriers } : {}),
  };
}

/**
 * The answer to one query of one result, under the page's filters. Pass null
 * for either to skip it, e.g. when nothing is being compared. The previous
 * answer stays on screen while a changed query loads.
 */
export function useResultQuery(query: CustomQuery | null, resultId: string | null): QueryState {
  const { filters } = useInspectFilters();
  const result = useCatalogueResult(resultId);
  const request: QueryRequest | null = query && result ? { query, result, filters } : null;
  const key = request
    ? [
        request.result.catalog,
        JSON.stringify(request.query),
        JSON.stringify(followedFilters(request)),
      ]
    : null;
  const { data, error, isLoading, mutate } = useResultRead(
    "query",
    key,
    () => resultSource.runQuery(request!),
    true,
  );
  return useMemo((): QueryState => {
    if (data) return { status: "ready", data, isRefreshing: isLoading };
    if (error !== undefined)
      return { status: "error", error: errorMessage(error), retry: () => void mutate() };
    return { status: "loading" };
  }, [data, error, isLoading, mutate]);
}

// ------------------------------------------------------------ Column values

/**
 * A computed table column's labels in a result, for the builder's value
 * pickers, read when first asked; null while loading (or if it failed).
 */
export function useColumnValues(
  queryName: string,
  column: string | null,
  resultId: string | null,
): string[] | null {
  const catalogue = useContext(ResultCatalogueContext);
  const result =
    catalogue?.results.find((item) => item.id === resultId) ?? catalogue?.results[0] ?? null;
  const { data } = useResultRead(
    "values",
    result && column ? [result.catalog, queryName, column] : null,
    () => loadColumnValues(result!, queryName, column!),
  );
  return data ?? null;
}
