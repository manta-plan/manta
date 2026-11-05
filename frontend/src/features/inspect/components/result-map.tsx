import { useMemo, useState } from "react";
import Map, {
  AttributionControl,
  Layer,
  ScaleControl,
  Source,
  type MapLayerMouseEvent,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { resultAreas, resultValueLabel, type ResultAreaValue } from "../lib/result-map-data";
import type { ResultCollection } from "../../project/data/result-collections";
import type { ViewState } from "../../project/store/types";
import { useProjectStore } from "../../project/store/project-store";
import { useAppStore } from "../../home/store";

const CARTO_BASEMAP_STYLE = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

const AREA_FILL_LAYER_ID = "result-areas-fill";
const RAMP_LOW = "#c6dbef";
const RAMP_HIGH = "#08519c";

function formatValue(value: number) {
  return value >= 100 ? Math.round(value).toLocaleString() : value.toFixed(1);
}

interface ResultMapProps {
  title: string;
  collection: ResultCollection;
  values: ResultAreaValue[];
  domain: [number, number];
  viewState: ViewState;
  onViewStateChange: (viewState: ViewState) => void;
  /** Areas picked by the bus filter; the others are dimmed. Empty highlights all. */
  highlightedNames?: string[];
}

export function ResultMap({
  title,
  collection,
  values,
  domain,
  viewState,
  onViewStateChange,
  highlightedNames = [],
}: ResultMapProps) {
  const theme = useAppStore((s) => s.theme);
  const record = useProjectStore((s) => s.record);
  const [hoveredArea, setHoveredArea] = useState<ResultAreaValue | null>(null);
  const valueLabel = resultValueLabel(collection);

  const areaData = useMemo(() => {
    const valueByName = new globalThis.Map(values.map((item) => [item.name, item.value]));
    return {
      type: "FeatureCollection" as const,
      features: resultAreas(record).map((area) => ({
        ...area,
        properties: { ...area.properties, value: valueByName.get(area.properties.name) ?? 0 },
      })),
    };
  }, [record, values]);

  // interpolate needs strictly ascending stops.
  const [low, high] = domain[1] > domain[0] ? domain : [domain[0], domain[0] + 1];

  const handleMouseMove = (event: MapLayerMouseEvent) => {
    const feature = event.features?.[0];
    const name = feature?.properties?.name as string | undefined;
    setHoveredArea(name ? (values.find((item) => item.name === name) ?? null) : null);
  };

  return (
    <section className="border-surface-700 bg-surface-900 relative min-h-0 min-w-0 flex-1 overflow-hidden border">
      <Map
        {...viewState}
        onMove={(event) => onViewStateChange(event.viewState)}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredArea(null)}
        interactiveLayerIds={[AREA_FILL_LAYER_ID]}
        cursor={hoveredArea ? "pointer" : undefined}
        mapStyle={CARTO_BASEMAP_STYLE[theme]}
        attributionControl={false}
        style={{ position: "absolute", inset: 0 }}
      >
        <Source id="result-areas" type="geojson" data={areaData}>
          <Layer
            id={AREA_FILL_LAYER_ID}
            type="fill"
            paint={{
              "fill-color": [
                "interpolate",
                ["linear"],
                ["get", "value"],
                low,
                RAMP_LOW,
                high,
                RAMP_HIGH,
              ],
              "fill-opacity": [
                "case",
                ["==", ["get", "name"], hoveredArea?.name ?? ""],
                0.85,
                highlightedNames.length === 0
                  ? true
                  : ["in", ["get", "name"], ["literal", highlightedNames]],
                0.6,
                0.12,
              ],
            }}
          />
          <Layer
            id="result-areas-outline"
            type="line"
            paint={{ "line-color": RAMP_HIGH, "line-width": 0.8, "line-opacity": 0.7 }}
          />
        </Source>
        <ScaleControl position="bottom-left" style={{ marginBottom: 48 }} />
        <AttributionControl position="bottom-right" compact style={{ marginBottom: 48 }} />
      </Map>

      {values.length > 0 && (
        <div className="border-surface-600 bg-surface-900/90 pointer-events-none absolute top-2 left-2 w-44 rounded border px-2 py-1.5 backdrop-blur">
          <div className="text-surface-400 truncate text-[10px] font-medium tracking-wide uppercase">
            {valueLabel}
          </div>
          <div
            className="mt-1 h-2 rounded-sm"
            style={{ background: `linear-gradient(to right, ${RAMP_LOW}, ${RAMP_HIGH})` }}
          />
          <div className="text-surface-400 mt-0.5 flex justify-between text-[10px] tabular-nums">
            <span>{formatValue(low)}</span>
            <span>{formatValue(high)}</span>
          </div>
          {hoveredArea && (
            <div className="border-surface-700 mt-1.5 border-t pt-1.5 text-[11px]">
              <div className="text-surface-100 truncate font-medium">{hoveredArea.name}</div>
              <div className="text-surface-300 tabular-nums">{formatValue(hoveredArea.value)}</div>
            </div>
          )}
        </div>
      )}

      {values.length === 0 && (
        <div className="text-surface-400 pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-[12px]">
          No model areas loaded for this project.
        </div>
      )}

      <div className="border-surface-700 bg-surface-900/95 absolute inset-x-0 bottom-0 flex h-10 items-center justify-between border-t px-3">
        <div className="min-w-0">
          <div className="text-surface-100 truncate text-[12px] font-medium">{title}</div>
          <div className="text-surface-400 truncate text-[11px]">{collection.label} by area</div>
        </div>
        <span className="text-surface-400 shrink-0 text-[11px]">{values.length} areas</span>
      </div>
    </section>
  );
}
