// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import useSWR, { unstable_serialize, type Cache, type State } from "swr";
import useSWRImmutable from "swr/immutable";
import { recordCatalog } from "./record-server/client";
import { isRunResult } from "./record-scenarios";
import { useProjectStore } from "../store/project-store";

// Reads from the record server, cached through SWR, for every tab: one cache
// (`<SWRConfig value={recordSWRConfig}>` at the app's root) of the most
// recently used entries.
// - A result never changes once solved, so what's read from its catalog is
//   cached for good: going back to a page or an item asks the server nothing.
// - Inputs come from a scenario, which may be edited one day: the cached
//   copy shows at once and is quietly refreshed when asked for again.
// Every key names its catalog (or record and scenario), so nothing is shared
// by mistake.
//
// The Inspect tab names catalogs itself (useResultData, useInputData). The
// Build tab's queries read the shown scenario's catalog, the one the client
// is set to (serverName): useShownData and readShown key by that catalog,
// and drop a read the client's catalog changed under (a scenario switch
// starting), rather than file it under the wrong one.

export type Loaded<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; data: T };

const CACHE_SIZE = 200;
// Time series can run to tens of thousands of points each (a year, hourly,
// per period): fewer of them are kept.
const SERIES_SIZE = 12;
const isSeries = (key: string) => key.includes('"series"');

/** SWR's cache, dropping the least recently used entry past `size` (and series past `seriesSize`). */
class RecentCache implements Cache {
  private entries = new Map<string, State>();
  private size: number;
  private seriesSize: number;
  constructor(size: number, seriesSize: number) {
    this.size = size;
    this.seriesSize = seriesSize;
  }

  keys() {
    return this.entries.keys();
  }

  get(key: string) {
    const value = this.entries.get(key);
    if (value !== undefined) {
      // Most recent last.
      this.entries.delete(key);
      this.entries.set(key, value);
    }
    return value;
  }

  set(key: string, value: State) {
    this.entries.delete(key);
    this.entries.set(key, value);
    while (this.entries.size > this.size) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.entries.delete(oldest);
    }
    if (!isSeries(key)) return;
    const series = [...this.entries.keys()].filter(isSeries);
    for (const oldest of series.slice(0, Math.max(0, series.length - this.seriesSize)))
      this.entries.delete(oldest);
  }

  delete(key: string) {
    this.entries.delete(key);
  }
}

const cache = new RecentCache(CACHE_SIZE, SERIES_SIZE);

/** For `<SWRConfig value={recordSWRConfig}>` around the app. */
export const recordSWRConfig = { provider: () => cache };

function loaded<T>(data: T | undefined, error: unknown): Loaded<T> {
  if (data !== undefined) return { status: "ready", data };
  if (error !== undefined)
    return { status: "error", error: error instanceof Error ? error.message : String(error) };
  return { status: "loading" };
}

/**
 * Something read from a result's catalog: cached for good. `name` says what
 * it is and `key` which (its catalog first); null skips.
 */
export function useResultData<T>(
  name: string,
  key: string | null,
  load: () => Promise<T>,
): Loaded<T> {
  const { data, error } = useSWRImmutable(
    key === null ? null : ["result", name, key],
    () => load(),
    { shouldRetryOnError: false },
  );
  return loaded(data, error);
}

/**
 * Something read from the shown scenario's inputs: the cached copy at once,
 * refreshed in the background when a page asks again. `key` names the record
 * and scenario; null skips.
 */
export function useInputData<T>(
  name: string,
  key: string | null,
  load: () => Promise<T>,
): Loaded<T> {
  const { data, error } = useSWR(key === null ? null : ["input", name, key], () => load(), {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    shouldRetryOnError: false,
  });
  return loaded(data, error);
}

// The Build tab: reads of the shown revision.

/** The client's catalog moved on while a read ran: not an error, the read is dropped. */
class CatalogMoved extends Error {
  constructor() {
    super("The shown scenario changed");
  }
}

/** `load`, run against `catalog`, or CatalogMoved if the client isn't (or stops being) on it. */
async function inCatalog<T>(catalog: string, load: () => Promise<T>): Promise<T> {
  if (recordCatalog() !== catalog) throw new CatalogMoved();
  const value = await load();
  if (recordCatalog() !== catalog) throw new CatalogMoved();
  return value;
}

/**
 * The shown revision's catalog, and whether it's a result (cached for good).
 * No catalog while a switch is under way: the client is set to the next
 * scenario before the app shows it.
 */
export function useShownCatalog(): { catalog: string | null; isResult: boolean } {
  const catalog = useProjectStore((s) =>
    s.switchingScenario || !s.record
      ? null
      : (s.record.info.revisions.find((r) => r.name === s.record?.scenario)?.catalog ?? null),
  );
  const isResult = useProjectStore((s) =>
    isRunResult(s.record?.info.revisions.find((r) => r.name === s.record?.scenario)),
  );
  return { catalog, isResult };
}

export type ShownData<T> = Loaded<T> & {
  /** The data shown is another scenario's, or being refreshed: newer is on its way. */
  refreshing: boolean;
};

/**
 * Something read from the shown scenario or result. `args` says which
 * (an entity, an attribute, …); null skips. While another scenario loads,
 * the last one's data for the same `args` stays, marked `refreshing`, rather
 * than a placeholder; data for other `args` never stands in.
 */
export function useShownData<T>(
  name: string,
  args: readonly unknown[] | null,
  load: () => Promise<T>,
): ShownData<T> {
  const { catalog, isResult } = useShownCatalog();
  const which = args === null ? null : unstable_serialize([name, ...args]);
  const key = which === null || catalog === null ? null : ["shown", name, catalog, ...args!];
  const { data, error, isValidating, isLoading } = useSWR(
    key,
    async () => ({ which, value: await inCatalog(catalog!, load) }),
    {
      keepPreviousData: true,
      revalidateIfStale: !isResult,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      shouldRetryOnError: false,
    },
  );
  if (which === null) return { status: "loading", refreshing: false };
  // Kept from an earlier key: only the same `args` in another scenario.
  const kept = data !== undefined && data.which === which ? data : undefined;
  // A switch, or a read dropped by one, isn't the reader's error.
  if (kept === undefined && error !== undefined && !(error instanceof CatalogMoved)) {
    return {
      status: "error",
      error: error instanceof Error ? error.message : String(error),
      refreshing: false,
    };
  }
  if (kept === undefined) return { status: "loading", refreshing: false };
  return {
    status: "ready",
    data: kept.value,
    refreshing: key === null || isLoading || isValidating,
  };
}

/**
 * For code that loads imperatively (the tree's folders): what's cached for
 * `args` in `catalog`, if anything, and a read that caches what it finds.
 * The read rejects with `isDropped` true when a switch began under it.
 */
export function readShown<T>(
  name: string,
  catalog: string,
  args: readonly unknown[],
  load: () => Promise<T>,
): { cached: T | undefined; read: () => Promise<T> } {
  const key = unstable_serialize(["shown-read", name, catalog, ...args]);
  const cached = cache.get(key)?.data as T | undefined;
  return {
    cached,
    read: () =>
      inCatalog(catalog, load).then((value) => {
        cache.set(key, { data: value });
        return value;
      }),
  };
}

export function isDropped(error: unknown): boolean {
  return error instanceof CatalogMoved;
}
