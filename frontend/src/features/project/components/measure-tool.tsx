import { useEffect, useState } from "react";
import { Layer, Source, useMap } from "react-map-gl/maplibre";
import type { MapMouseEvent } from "maplibre-gl";
import { LuEraser, LuRuler, LuSquareDashed, LuX } from "react-icons/lu";
import {
  MEASURE_FILL_LAYER_ID,
  MEASURE_LINE_LAYER_ID,
  MEASURE_VERTEX_LAYER_ID,
  formatArea,
  formatDistance,
  measure,
  measureGeometry,
  type LngLat,
  type MeasureMode,
} from "../lib/measure";

// Amber reads against the dark, light and satellite basemaps alike.
const MEASURE_COLOR = "#f59e0b";
// The two clicks of a double-click land a pixel or two apart; don't count
// the second one as a new vertex.
const DUPLICATE_CLICK_PX = 4;

interface MeasureState {
  points: LngLat[];
  isFinished: boolean;
}

const EMPTY: MeasureState = { points: [], isFinished: false };

/**
 * Click to add vertices, double-click to finish, Esc to clear (or exit when
 * there's nothing to clear). Rendered as a child of <Map>; remount it (via
 * `key`) to reset when the mode changes.
 */
export function MeasureTool({ mode, onExit }: { mode: MeasureMode; onExit: () => void }) {
  const { current: mapRef } = useMap();
  const [state, setState] = useState<MeasureState>(EMPTY);
  const [hover, setHover] = useState<LngLat | null>(null);
  const minPoints = mode === "area" ? 3 : 2;

  useEffect(() => {
    const map = mapRef?.getMap();
    if (!map) return;

    const handleClick = (e: MapMouseEvent) => {
      const point: LngLat = [e.lngLat.lng, e.lngLat.lat];
      setState((prev) => {
        if (prev.isFinished) return { points: [point], isFinished: false };
        const last = prev.points.at(-1);
        if (last && map.project(last).dist(e.point) < DUPLICATE_CLICK_PX) return prev;
        return { points: [...prev.points, point], isFinished: false };
      });
    };
    const handleDoubleClick = (e: MapMouseEvent) => {
      e.preventDefault();
      setState((prev) => (prev.points.length >= minPoints ? { ...prev, isFinished: true } : prev));
    };
    const handleMouseMove = (e: MapMouseEvent) => setHover([e.lngLat.lng, e.lngLat.lat]);
    const handleMouseOut = () => setHover(null);

    map.on("click", handleClick);
    map.on("dblclick", handleDoubleClick);
    map.on("mousemove", handleMouseMove);
    map.on("mouseout", handleMouseOut);
    return () => {
      map.off("click", handleClick);
      map.off("dblclick", handleDoubleClick);
      map.off("mousemove", handleMouseMove);
      map.off("mouseout", handleMouseOut);
    };
  }, [mapRef, minPoints]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (state.points.length > 0) setState(EMPTY);
      else onExit();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onExit, state.points.length]);

  // While drawing, the cursor acts as a provisional next vertex so the
  // readout updates live.
  const displayPoints =
    !state.isFinished && hover && state.points.length > 0 ? [...state.points, hover] : state.points;
  const geometry = measureGeometry(displayPoints, mode);
  const result = measure(displayPoints, mode);
  const hasResult = displayPoints.length >= minPoints;

  const hint =
    state.points.length === 0
      ? "Click the map to start measuring"
      : state.isFinished
        ? "Click to start a new measurement"
        : "Click to add a point · double-click to finish · Esc to clear";

  return (
    <>
      <Source id="measure" type="geojson" data={geometry}>
        <Layer
          id={MEASURE_FILL_LAYER_ID}
          type="fill"
          filter={["==", ["geometry-type"], "Polygon"]}
          paint={{ "fill-color": MEASURE_COLOR, "fill-opacity": 0.15 }}
        />
        <Layer
          id={MEASURE_LINE_LAYER_ID}
          type="line"
          filter={["!=", ["geometry-type"], "Point"]}
          layout={{ "line-join": "round", "line-cap": "round" }}
          paint={{ "line-color": MEASURE_COLOR, "line-width": 2, "line-dasharray": [2, 1.5] }}
        />
        <Layer
          id={MEASURE_VERTEX_LAYER_ID}
          type="circle"
          filter={["==", ["geometry-type"], "Point"]}
          paint={{
            "circle-radius": 4,
            "circle-color": "#ffffff",
            "circle-stroke-color": MEASURE_COLOR,
            "circle-stroke-width": 2,
          }}
        />
      </Source>

      <div className="border-surface-600 bg-surface-800/95 text-surface-100 absolute top-3 left-1/2 z-10 flex -translate-x-1/2 items-start gap-3 rounded-md border px-3 py-2 shadow-lg shadow-black/30">
        {mode === "area" ? (
          <LuSquareDashed size={16} className="text-surface-300 mt-0.5 shrink-0" />
        ) : (
          <LuRuler size={16} className="text-surface-300 mt-0.5 shrink-0" />
        )}
        <div className="min-w-[180px]">
          <div className="flex items-baseline gap-3 tabular-nums">
            {mode === "area" ? (
              <>
                <span className="text-[14px] font-semibold">
                  {hasResult ? formatArea(result.area) : "—"}
                </span>
                {hasResult && (
                  <span className="text-surface-400 text-[11px]">
                    Perimeter {formatDistance(result.distance)}
                  </span>
                )}
              </>
            ) : (
              <span className="text-[14px] font-semibold">
                {hasResult ? formatDistance(result.distance) : "—"}
              </span>
            )}
          </div>
          <div className="text-surface-400 mt-0.5 text-[11px]">{hint}</div>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            title="Clear measurement"
            aria-label="Clear measurement"
            disabled={state.points.length === 0}
            onClick={() => setState(EMPTY)}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 items-center justify-center rounded disabled:pointer-events-none disabled:opacity-40"
          >
            <LuEraser size={14} />
          </button>
          <button
            type="button"
            title="Close measure tool"
            aria-label="Close measure tool"
            onClick={onExit}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 items-center justify-center rounded"
          >
            <LuX size={14} />
          </button>
        </div>
      </div>
    </>
  );
}
