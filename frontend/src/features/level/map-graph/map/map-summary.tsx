import { useLevelPage } from "../../level-page-context";
import {
  mapSummaryOf,
  useBranches,
  useBuses,
  useHighlight,
  useSites,
  type MapSummary,
} from "../map-graph-data";
import { useMapLayerStore } from "./map-layer-store";

// The map's line in the Map & graph header: what the level highlights.
// Reads what the map reads (the same cached queries), so it costs no request.

const n = (value: number) => value.toLocaleString();

/** The summary as one line of text. */
export function mapSummaryText(summary: MapSummary, showSiting: boolean): string {
  const parts = [
    `${n(summary.buses)} of ${n(summary.allBuses)} buses` +
      (summary.lineEnds > 0 ? `, ${n(summary.lineEnds)} line ends` : ""),
    `${n(summary.lines)} of ${n(summary.allLines)} lines`,
  ];
  if (summary.located !== null)
    parts.push(
      `${n(summary.located)} of ${n(summary.members)} entities have their own location` +
        (summary.located > 0
          ? showSiting
            ? "; dashed lines join them to their bus"
            : "; siting hidden"
          : ""),
    );
  return parts.join(" · ");
}

/** The summary line, or nothing until the buses and the highlight are read. */
export function useMapSummaryLine(): string | null {
  const { level, scope } = useLevelPage();
  const showSiting = useMapLayerStore((s) => s.showSiting);
  const busesData = useBuses();
  const buses = busesData.status === "ready" ? busesData.data : null;
  const branchesData = useBranches(scope);
  const branches = branchesData.status === "ready" ? branchesData.data : null;
  const sitesData = useSites(scope);
  const sites = sitesData.status === "ready" ? sitesData.data : null;
  const highlight = useHighlight(level, scope, buses, branches);
  if (!highlight || !buses) return null;
  return mapSummaryText(mapSummaryOf(level, highlight, buses, branches, sites), showSiting);
}
