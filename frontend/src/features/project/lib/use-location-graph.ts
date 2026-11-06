import { useEffect, useMemo, useState } from "react";
import { zoneOf } from "./record-geo";
import type { GraphContext } from "./location-graph";
import { getLocationGraph } from "./record-server/queries";
import type { LocationGraphRows } from "./record-server/types";
import { useProjectStore } from "../store/project-store";

const cache = new Map<string, Promise<LocationGraphRows>>();

// The rows behind a place's graph, fetched once per place and scenario per
// page load.
export function useLocationGraphRows(locations: string[]): {
  rows: LocationGraphRows | null;
  error: string | null;
} {
  const scenario = useProjectStore((s) => s.record?.scenario ?? "");
  const places = [...locations].sort().join("\n");
  const key = places && `${scenario}\t${places}`;
  const [state, setState] = useState<{
    key: string;
    rows: LocationGraphRows | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    let request = cache.get(key);
    if (!request) {
      request = getLocationGraph(places.split("\n"));
      cache.set(key, request);
      request.catch(() => cache.delete(key));
    }
    request
      .then((rows) => !cancelled && setState({ key, rows, error: null }))
      .catch(
        (error: unknown) =>
          !cancelled &&
          setState({
            key,
            rows: null,
            error: error instanceof Error ? error.message : String(error),
          }),
      );
    return () => {
      cancelled = true;
    };
    // The key names what's fetched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state?.key === key ? state : { rows: null, error: null };
}

export function useGraphContext(locations: string[]): GraphContext | null {
  const record = useProjectStore((s) => s.record);
  const resolution = useProjectStore((s) => s.resolution);
  return useMemo(() => {
    if (!record) return null;
    const zones = zoneOf(record, resolution);
    return {
      inside: new Set(locations),
      real: new Set(record.locations.map((location) => location.location)),
      placeOf: (location) => zones.get(location) ?? location,
      carrierColor: (carrier) => (carrier ? (record.carriers[carrier]?.color ?? null) : null),
      carrierName: (carrier) => (carrier ? record.carriers[carrier]?.niceName || carrier : "—"),
    };
  }, [locations, record, resolution]);
}
