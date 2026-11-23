/* eslint-disable react-hooks/exhaustive-deps -- several memos and effects key on a derived value (joined coordinates, the fit key, the highlight) because the object they read is rebuilt each render; each says which. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, {
  AttributionControl,
  Layer,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type { GeoJSONSource } from "maplibre-gl";
import { Toolbar } from "@base-ui/react/toolbar";
import {
  LuBan,
  LuCompass,
  LuEarth,
  LuFrame,
  LuMinus,
  LuMoon,
  LuPlus,
  LuRuler,
  LuSatellite,
  LuSquare,
  LuSquareDashedMousePointer,
  LuSun,
  LuX,
  LuMapPin,
} from "react-icons/lu";
import { MapLoadingOverlay } from "../../../project/components/map-loading-overlay";
import { MeasureTool } from "../../../project/components/measure-tool";
import { ToolbarIconButton } from "../../../project/components/toolbar-icon-button";
import {
  ToolbarModeMenu,
  type ToolbarModeOption,
} from "../../../project/components/toolbar-mode-menu";
import type { MeasureMode } from "../../../project/lib/measure";
import { useProjectStore } from "../../../project/store/project-store";
import type { BasemapId, ToolId } from "../../../project/store/types";
import { levelPageId } from "../../level";
import { useLevelPage } from "../../level-page-context";
import { useLevelStore } from "../../level-store";
import {
  useAreaName,
  useBranches,
  useBuses,
  useFocusTarget,
  useHighlight,
  useRegions,
  useRoutes,
  useSites,
  type RegionRow,
} from "../map-graph-data";
import { boundsOf, locationPoints, padBounds, type Bounds, type LngLat } from "./map-geo";
import { MapLayersPopover } from "./map-layers-popover";
import { MapLegend, type LegendSpec } from "./map-legends";
import { needsResults, rampColor, regionShadingLabel, useMapLayerStore } from "./map-layer-store";
import { useLineColouring, useRegionShading, type LayerValues } from "./map-shading";
import { BASEMAP_STYLE, COLORS, diamondIcon, drawDiamond } from "./map-style";
import { useBoxSelect } from "./use-box-select";

// Map & graph's map: bus regions (onshore solid, offshore dashed and
// fainter), location points, lines between locations and located entities,
// over a CARTO or Esri basemap. The level highlights its members' buses and
// lines (the far ends grey); at a location, bus or entity the map zooms to
// them. A click opens a location or a line; Shift+drag, "Select locations"
// and Ctrl/⌘+click select locations for the table.

const LAYER = {
  regionFill: "level-regions-fill",
  regionLine: "level-regions-line",
  regionLineOffshore: "level-regions-line-offshore",
  branches: "level-branches",
  routeHalo: "level-route-halo",
  routeStroke: "level-route-stroke",
  siteLinks: "level-site-links",
  points: "level-points",
  sites: "level-sites",
  pulse: "level-pulse",
  labels: "level-labels",
};
const NO_REGIONS: RegionRow[] = [];
const PULSE_SOURCE = "level-pulse-source";
const LEVEL_PADDING = 0.18;
const ZOOMABLE = new Set(["location", "bus", "entity"]);

const MEASURE_OPTIONS: ToolbarModeOption<ToolId>[] = [
  { value: "select", label: "Off", icon: LuBan },
  { value: "measure-distance", label: "Distance", icon: LuRuler },
  { value: "measure-area", label: "Area", icon: LuSquare },
];
const BASEMAP_OPTIONS: ToolbarModeOption<BasemapId>[] = [
  { value: "vector-dark", label: "Dark", icon: LuMoon },
  { value: "vector-light", label: "Light", icon: LuSun },
  { value: "satellite", label: "Satellite", icon: LuSatellite },
];
const PANEL_CLASS =
  "rounded-md border border-surface-600 bg-surface-800/95 shadow-lg shadow-black/30 backdrop-blur-sm";

type Feature<P, G> = { type: "Feature"; properties: P; geometry: G };
const collection = <P, G>(features: Feature<P, G>[]) => ({
  type: "FeatureCollection" as const,
  features,
});
const point = (coordinates: LngLat) => ({ type: "Point" as const, coordinates });
const line = (coordinates: LngLat[]) => ({ type: "LineString" as const, coordinates });

/** The 0–1 position of each value between the layer's min and max. */
function scaleOf(layer: LayerValues | null) {
  const values = layer ? [...layer.values.values()] : [];
  const min = values.length > 0 ? Math.min(...values) : null;
  const max = values.length > 0 ? Math.max(...values) : null;
  const at = (value: number) =>
    min !== null && max !== null && max > min ? (value - min) / (max - min) : 0;
  return { min, max, at };
}

export function LevelMap() {
  const { level, scope, result, openLevel } = useLevelPage();
  const withResults = result !== null;
  const record = useProjectStore((s) => s.record);
  const viewState = useProjectStore((s) => s.viewState);
  const setViewState = useProjectStore((s) => s.setViewState);
  const setCursorPosition = useProjectStore((s) => s.setCursorPosition);
  const basemap = useProjectStore((s) => s.basemap);
  const setBasemap = useProjectStore((s) => s.setBasemap);
  const activeTool = useProjectStore((s) => s.activeTool);
  const setActiveTool = useProjectStore((s) => s.setActiveTool);
  const appFocus = useProjectStore((s) => s.mapFocus);
  const selectedLocations = useLevelStore((s) => s.selectedLocations);
  const setSelectedLocations = useLevelStore((s) => s.setSelectedLocations);
  const toggleSelectedLocation = useLevelStore((s) => s.toggleSelectedLocation);
  const mapFocus = useLevelStore((s) => s.mapFocus);
  const setMapFocus = useLevelStore((s) => s.setMapFocus);
  const layers = useMapLayerStore();

  const mapRef = useRef<MapRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isHovering, setIsHovering] = useState(false);
  // The loading overlay fades out once the basemap and the buses are in, then goes.
  const [showOverlay, setShowOverlay] = useState(true);
  // 'level' frames the level's features (where it has a place), 'all' the whole record.
  const [fit, setFit] = useState<"level" | "all">("level");
  // A zoom or pan by hand since the last fit.
  const [isManual, setIsManual] = useState(false);
  const [refit, setRefit] = useState(0);

  const pageId = levelPageId(level);
  const zoomable = ZOOMABLE.has(level.kind);
  useEffect(() => {
    setFit("level");
    setIsManual(false);
  }, [pageId]);

  // Keep the map the block's size.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => mapRef.current?.resize());
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const measureMode: MeasureMode | null =
    activeTool === "measure-distance" ? "distance" : activeTool === "measure-area" ? "area" : null;
  const exitMeasure = useCallback(() => setActiveTool("select"), [setActiveTool]);
  // Leaving the map ends measuring (nothing else would turn it off).
  useEffect(() => exitMeasure, [exitMeasure]);

  // ---------------------------------------------------------- Data

  const busesData = useBuses();
  const buses = busesData.status === "ready" ? busesData.data : null;
  const regionsData = useRegions();
  const regions = regionsData.status === "ready" ? regionsData.data : NO_REGIONS;
  const branchesData = useBranches(scope);
  const branches = branchesData.status === "ready" ? branchesData.data : null;
  const routesData = useRoutes();
  const routes = routesData.status === "ready" ? routesData.data : null;
  const sitesData = useSites(scope);
  const sites = sitesData.status === "ready" ? sitesData.data : null;
  const highlight = useHighlight(level, scope, buses, branches);
  const areaName = useAreaName();

  const focusEntity = mapFocus?.entity ?? (level.kind === "entity" ? level.entity : null);
  const focusData = useFocusTarget(scope, focusEntity);
  const target = focusData.status === "ready" ? focusData.data : null;

  const shadingOn =
    layers.regionShading !== null && (withResults || !needsResults(layers.regionShading))
      ? layers.regionShading
      : null;
  const colouringOn =
    layers.lineColouring !== null && (withResults || !needsResults(layers.lineColouring))
      ? layers.lineColouring
      : null;
  const shadingData = useRegionShading(scope, shadingOn, withResults);
  const colouringData = useLineColouring(scope, colouringOn, withResults);
  const shading = shadingOn && shadingData.status === "ready" ? shadingData.data : null;
  const colouring = colouringOn && colouringData.status === "ready" ? colouringData.data : null;

  const points = useMemo(() => locationPoints(buses ?? []), [buses]);
  const selected = useMemo(() => new Set(selectedLocations), [selectedLocations]);
  const carrierColor = useCallback(
    (carrier: string | null) => (carrier && record?.carriers[carrier]?.color) || COLORS.accentLight,
    [record],
  );

  const lines = useMemo(
    () => branches?.filter((branch) => branch.ctype === "Line") ?? [],
    [branches],
  );
  const isLit = (entity: string) =>
    Boolean(highlight && (highlight.all || highlight.lines.has(entity)));
  const ends = useMemo(() => {
    const found = new Set<string>();
    if (!highlight || highlight.all) return found;
    for (const branch of lines) {
      if (!highlight.lines.has(branch.entity)) continue;
      for (const location of [branch.location0, branch.location1])
        if (!highlight.locations.has(location)) found.add(location);
    }
    return found;
  }, [highlight, lines]);

  // ---------------------------------------------------------- Features

  const shadeScale = useMemo(() => scaleOf(shading), [shading]);
  const regionFeatures = useMemo(
    () =>
      collection(
        regions.map((region) => {
          const location = region.location ?? "";
          const offshore = region.component === "offshore";
          const on = Boolean(highlight && (highlight.all || highlight.locations.has(location)));
          let fill = on ? COLORS.accent : COLORS.muted;
          let fillOpacity = on ? 0.22 : 0.07;
          let stroke = on ? COLORS.accentLight : COLORS.muted;
          let strokeOpacity = on ? 0.9 : 0.45;
          let width = on ? 1.2 : 0.6;
          const value = shading?.values.get(location);
          if (shading) {
            fill = value === undefined ? COLORS.muted : rampColor(shadeScale.at(value));
            fillOpacity = value === undefined ? 0.06 : 0.62;
          }
          if (selected.has(location)) {
            fill = COLORS.halo;
            fillOpacity = 0.38;
            stroke = COLORS.halo;
            strokeOpacity = 1;
            width = 1.8;
          }
          // Offshore regions: fainter.
          if (offshore) fillOpacity *= 0.7;
          return {
            type: "Feature" as const,
            properties: { location, offshore, fill, fillOpacity, stroke, strokeOpacity, width },
            geometry: region.geometry,
          };
        }),
      ),
    [regions, highlight, shading, shadeScale, selected],
  );

  const lineScale = useMemo(() => scaleOf(colouring), [colouring]);
  const showLines = layers.showTopology || colouring !== null;
  const branchFeatures = useMemo(() => {
    if (!branches) return collection<{ entity: string }, ReturnType<typeof line>>([]);
    return collection(
      branches.flatMap((branch) => {
        const a = points.get(branch.location0);
        const b = points.get(branch.location1);
        if (!a || !b) return [];
        const coordinates = routes?.get(branch.entity) ?? [a, b];
        const on = isLit(branch.entity);
        const value = colouring?.values.get(branch.entity);
        const capacity = branch.capacity_opt ?? branch.capacity ?? 0;
        let color = on ? COLORS.line : COLORS.muted;
        let width = on ? Math.min(6, 1 + capacity / 2000) : 0.8;
        let opacity = on ? 0.95 : 0.45;
        if (colouring && branch.ctype === "Line") {
          const t = value === undefined ? 0 : lineScale.at(value);
          color = value === undefined ? COLORS.muted : rampColor(t);
          width = 1.2 + t * 4;
          opacity = 0.95;
        }
        return [
          {
            type: "Feature" as const,
            properties: { entity: branch.entity, ctype: branch.ctype, color, width, opacity },
            geometry: line(coordinates),
          },
        ];
      }),
    );
    // isLit reads highlight.
  }, [branches, points, routes, highlight, colouring, lineScale]);

  const pointFeatures = useMemo(
    () =>
      collection(
        [...points].map(([location, coordinates]) => {
          const state =
            highlight?.all || highlight?.locations.has(location)
              ? "on"
              : ends.has(location)
                ? "end"
                : "off";
          return {
            type: "Feature" as const,
            properties: { location, state, label: location },
            geometry: point(coordinates),
          };
        }),
      ),
    [points, highlight, ends],
  );
  const showLabels = Boolean(highlight && !highlight.all && highlight.buses.size <= 6);

  const siteFeatures = useMemo(() => {
    const shown = (sites ?? []).filter((site) => layers.showSiting || site.entity === focusEntity);
    const diamonds = shown.map((site) => ({
      type: "Feature" as const,
      properties: {
        entity: site.entity,
        icon: diamondIcon(carrierColor(site.carrier)),
        size: site.entity === focusEntity ? 1.1 : 0.75,
      },
      geometry: point([site.lon, site.lat]),
    }));
    const links = shown.flatMap((site) => {
      const bus = site.location ? points.get(site.location) : undefined;
      if (!bus || !(layers.showTopology || site.entity === focusEntity)) return [];
      return [
        {
          type: "Feature" as const,
          properties: { color: carrierColor(site.carrier), focused: site.entity === focusEntity },
          geometry: line([[site.lon, site.lat], bus]),
        },
      ];
    });
    // The focused entity's site, when it isn't one of the level's.
    if (target?.site && !shown.some((site) => site.entity === target.entity)) {
      diamonds.push({
        type: "Feature",
        properties: {
          entity: target.entity,
          icon: diamondIcon(carrierColor(target.carrier)),
          size: 1.1,
        },
        geometry: point(target.site),
      });
      const bus = target.location ? points.get(target.location) : undefined;
      if (bus)
        links.push({
          type: "Feature",
          properties: { color: carrierColor(target.carrier), focused: true },
          geometry: line([target.site, bus]),
        });
    }
    return { diamonds: collection(diamonds), links: collection(links) };
  }, [sites, layers.showSiting, layers.showTopology, focusEntity, carrierColor, points, target]);

  // The focused route (a branch), or the pulsing ring at the focused entity's site or bus.
  const routeFeatures = useMemo(() => {
    if (!target || !branches) return null;
    const own = branches.filter((branch) => branch.entity === target.entity);
    if (own.length === 0) return null;
    return collection(
      own.flatMap((branch) => {
        const a = points.get(branch.location0);
        const b = points.get(branch.location1);
        return a && b
          ? [
              {
                type: "Feature" as const,
                properties: {},
                geometry: line(routes?.get(branch.entity) ?? [a, b]),
              },
            ]
          : [];
      }),
    );
  }, [target, branches, points, routes]);
  const pulseAt: LngLat | null =
    target && !routeFeatures
      ? (target.site ?? (target.location ? (points.get(target.location) ?? null) : null))
      : null;
  const pulseColor = mapFocus ? COLORS.halo : carrierColor(target?.carrier ?? null);

  useEffect(() => {
    if (!isLoaded || !pulseAt) return;
    let frame = 0;
    const startedAt = performance.now();
    const animate = (now: number) => {
      const source = mapRef.current?.getMap().getSource(PULSE_SOURCE) as GeoJSONSource | undefined;
      const pulse = ((now - startedAt) % 1600) / 1600;
      source?.setData(
        collection([
          {
            type: "Feature" as const,
            properties: { pulse, color: pulseColor },
            geometry: point(pulseAt),
          },
        ]),
      );
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
    // pulseAt is a new array each render; its text says when it moved.
  }, [isLoaded, pulseAt?.join(","), pulseColor]);

  // ---------------------------------------------------------- Fit

  const allBounds = useMemo(() => {
    const found = boundsOf(points.values());
    return found && padBounds(found, 0.04);
  }, [points]);

  const levelBounds = useMemo((): Bounds | null => {
    if (!zoomable || !highlight) return null;
    const lit: LngLat[] = [];
    for (const location of [...highlight.locations, ...ends]) {
      const at = points.get(location);
      if (at) lit.push(at);
    }
    for (const site of sites ?? []) lit.push([site.lon, site.lat]);
    const found = boundsOf(lit);
    return found && padBounds(found, LEVEL_PADDING);
  }, [zoomable, highlight, ends, points, sites]);

  const focusBounds = useMemo((): Bounds | null => {
    if (!mapFocus || !target) return null;
    const at: LngLat[] = [];
    for (const location of [target.location, target.location1]) {
      const found = location ? points.get(location) : undefined;
      if (found) at.push(found);
    }
    if (target.site) at.push(target.site);
    for (const coordinates of routeFeatures?.features.flatMap(
      (feature) => feature.geometry.coordinates,
    ) ?? [])
      at.push(coordinates);
    const found = boundsOf(at);
    return found && padBounds(found, 0.35, 0.05);
  }, [mapFocus, target, points, routeFeatures]);

  const wanted = focusBounds ?? (fit === "level" && levelBounds ? levelBounds : allBounds);
  const wantedKey = wanted
    ? wanted
        .flat()
        .map((n) => n.toFixed(4))
        .join(",")
    : null;
  useEffect(() => {
    const map = mapRef.current;
    if (!isLoaded || !map || !wanted) return;
    setIsManual(false);
    map.fitBounds(wanted, { padding: 16, duration: 600, maxZoom: 12 });
    // wanted is rebuilt each render; wantedKey says when it changed.
  }, [isLoaded, wantedKey, refit]);

  // "Zoom to Area of Interest" (View menu): the whole record.
  const lastAppFocus = useRef(appFocus?.at);
  useEffect(() => {
    if (!appFocus || appFocus.at === lastAppFocus.current) return;
    lastAppFocus.current = appFocus.at;
    setMapFocus(null);
    setFit("all");
    setRefit((n) => n + 1);
  }, [appFocus, setMapFocus]);

  const onMoveStart = (event: ViewStateChangeEvent) => {
    // A move the user started (wheel, drag), not a fit.
    if (event.originalEvent) setIsManual(true);
  };

  const onFrame = () => {
    if (mapFocus) setMapFocus(null);
    else if (!isManual && zoomable) setFit(fit === "level" ? "all" : "level");
    setRefit((n) => n + 1);
  };
  const area = areaName ?? "the record";
  const showAll = `Show all of ${area}`;
  // Back to the fit shown after a manual move or a focus; else the other fit.
  const frameLabel = !zoomable
    ? showAll
    : isManual || mapFocus
      ? fit === "level"
        ? "Zoom to this level"
        : showAll
      : fit === "level"
        ? showAll
        : "Zoom to this level";

  // ---------------------------------------------------------- Interaction

  const box = useBoxSelect({
    mapRef,
    isLoaded,
    isSelecting: layers.isSelecting,
    points,
    selected: selectedLocations,
    onSelect: setSelectedLocations,
  });

  const onClick = (event: MapLayerMouseEvent) => {
    if (measureMode) return;
    const feature = event.features?.[0];
    if (!feature) return;
    const layerId = feature.layer.id;
    const properties = feature.properties as Record<string, unknown>;
    if (layerId === LAYER.points || layerId === LAYER.regionFill) {
      const location = String(properties.location ?? "");
      if (!location) return;
      if (event.originalEvent.ctrlKey || event.originalEvent.metaKey)
        toggleSelectedLocation(location);
      else openLevel({ kind: "location", location });
    } else if (layerId === LAYER.branches || layerId === LAYER.sites) {
      openLevel({ kind: "entity", entity: String(properties.entity) });
    }
  };

  // Diamond markers, one image per carrier colour: drawn up front (and again
  // after a basemap switch drops them), and on demand for any other.
  const addDiamond = useCallback((id: string) => {
    const map = mapRef.current?.getMap();
    const image = drawDiamond(id);
    if (map && image && !map.hasImage(id)) map.addImage(id, image, { pixelRatio: 2 });
  }, []);
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!isLoaded || !map) return;
    const colors = [
      COLORS.accentLight,
      ...Object.values(record?.carriers ?? {}).flatMap((carrier) =>
        carrier.color ? [carrier.color] : [],
      ),
    ];
    const addAll = () => colors.forEach((color) => addDiamond(diamondIcon(color)));
    const onMissing = (event: { id: string }) => addDiamond(event.id);
    addAll();
    map.on("style.load", addAll);
    map.on("styleimagemissing", onMissing);
    return () => {
      map.off("style.load", addAll);
      map.off("styleimagemissing", onMissing);
    };
  }, [isLoaded, record, addDiamond]);

  const zoomBy = (delta: number) =>
    mapRef.current?.getMap().zoomTo(Math.max(0, viewState.zoom + delta), { duration: 250 });
  const rotated = viewState.bearing !== 0 || viewState.pitch !== 0;
  const nodeStroke = basemap === "vector-light" ? "#ffffff" : "#0a0d12";

  // ---------------------------------------------------------- Legends and caption

  const legends: LegendSpec[] = [];
  if (shadingOn) {
    legends.push({
      name: regionShadingLabel(shadingOn),
      min: shadeScale.min,
      max: shadeScale.max,
      unit: shading?.unit ?? "",
      percent: shading?.percent ?? false,
      loading: shadingData.status === "loading",
      empty: withResults ? "none in this run result" : "none existing in the inputs; see Inspect",
    });
  }
  if (colouringOn) {
    legends.push({
      name: colouringOn === "capacity" ? "Line · Capacity" : "Line · Loading",
      min: lineScale.min,
      max: lineScale.max,
      unit: colouring?.unit ?? "",
      percent: colouring?.percent ?? false,
      loading: colouringData.status === "loading",
      empty: withResults ? "none in this run result" : "none existing in the inputs; see Inspect",
    });
  }

  const memberCount = level.kind === "entity" ? 1 : (highlight?.members ?? 0);
  const located = sites?.length ?? 0;
  const litLines = highlight ? lines.filter((branch) => isLit(branch.entity)).length : 0;

  const interactive = measureMode
    ? []
    : [
        LAYER.regionFill,
        ...(showLines ? [LAYER.branches] : []),
        ...(layers.showTopology ? [LAYER.points] : []),
        LAYER.sites,
      ];

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <Map
        ref={mapRef}
        {...viewState}
        onMove={(event) => setViewState(event.viewState)}
        onMoveStart={onMoveStart}
        onLoad={() => setIsLoaded(true)}
        onMouseMove={(event) => {
          setCursorPosition({ lng: event.lngLat.lng, lat: event.lngLat.lat });
          setIsHovering((event.features?.length ?? 0) > 0);
        }}
        onMouseLeave={() => {
          setCursorPosition(null);
          setIsHovering(false);
        }}
        onClick={onClick}
        boxZoom={false}
        dragPan={!layers.isSelecting}
        doubleClickZoom={!measureMode}
        interactiveLayerIds={interactive}
        cursor={
          measureMode || layers.isSelecting ? "crosshair" : isHovering ? "pointer" : undefined
        }
        mapStyle={BASEMAP_STYLE[basemap]}
        attributionControl={false}
        style={{ width: "100%", height: "100%" }}
      >
        <Source id="level-regions" type="geojson" data={regionFeatures}>
          <Layer
            id={LAYER.regionFill}
            type="fill"
            paint={{ "fill-color": ["get", "fill"], "fill-opacity": ["get", "fillOpacity"] }}
          />
          <Layer
            id={LAYER.regionLine}
            type="line"
            filter={["!", ["get", "offshore"]]}
            paint={{
              "line-color": ["get", "stroke"],
              "line-opacity": ["get", "strokeOpacity"],
              "line-width": ["get", "width"],
            }}
          />
          <Layer
            id={LAYER.regionLineOffshore}
            type="line"
            filter={["get", "offshore"]}
            paint={{
              "line-color": ["get", "stroke"],
              "line-opacity": ["*", 0.75, ["get", "strokeOpacity"]],
              "line-width": ["get", "width"],
              "line-dasharray": [3, 2],
            }}
          />
        </Source>

        <Source id="level-branches" type="geojson" data={branchFeatures}>
          <Layer
            id={LAYER.branches}
            type="line"
            layout={{
              "line-cap": "round",
              "line-join": "round",
              visibility: showLines ? "visible" : "none",
            }}
            paint={{
              "line-color": ["get", "color"],
              "line-width": ["get", "width"],
              "line-opacity": ["get", "opacity"],
            }}
          />
        </Source>

        {routeFeatures && (
          <Source id="level-route" type="geojson" data={routeFeatures}>
            <Layer
              id={LAYER.routeHalo}
              type="line"
              layout={{ "line-cap": "round" }}
              paint={{
                "line-color": COLORS.halo,
                "line-width": 10,
                "line-opacity": 0.28,
                "line-blur": 1.5,
              }}
            />
            <Layer
              id={LAYER.routeStroke}
              type="line"
              layout={{ "line-cap": "round" }}
              paint={{ "line-color": COLORS.halo, "line-width": 3.5, "line-opacity": 0.95 }}
            />
          </Source>
        )}

        <Source id="level-site-links" type="geojson" data={siteFeatures.links}>
          <Layer
            id={LAYER.siteLinks}
            type="line"
            paint={{
              "line-color": ["get", "color"],
              "line-width": ["case", ["get", "focused"], 2, 1.1],
              "line-opacity": ["case", ["get", "focused"], 1, 0.75],
              "line-dasharray": [3, 2.5],
            }}
          />
        </Source>

        <Source id="level-points" type="geojson" data={pointFeatures}>
          <Layer
            id={LAYER.points}
            type="circle"
            layout={{ visibility: layers.showTopology ? "visible" : "none" }}
            paint={{
              "circle-radius": ["match", ["get", "state"], "on", 4.5, "end", 3.6, 2.6],
              "circle-color": [
                "match",
                ["get", "state"],
                "on",
                COLORS.accent,
                "end",
                COLORS.farEnd,
                COLORS.muted,
              ],
              "circle-opacity": ["match", ["get", "state"], "off", 0.7, 1],
              "circle-stroke-width": 1.2,
              "circle-stroke-color": nodeStroke,
            }}
          />
          <Layer
            id={LAYER.labels}
            type="symbol"
            filter={["==", ["get", "state"], "on"]}
            layout={{
              visibility: showLabels ? "visible" : "none",
              "text-field": ["get", "label"],
              "text-size": 11,
              "text-offset": [0.6, -0.6],
              "text-anchor": "bottom-left",
            }}
            paint={{
              "text-color": basemap === "vector-light" ? "#1f2937" : "#e5e7eb",
              "text-halo-color": basemap === "vector-light" ? "#ffffff" : "#000000",
              "text-halo-width": 1.5,
            }}
          />
        </Source>

        <Source id="level-sites" type="geojson" data={siteFeatures.diamonds}>
          <Layer
            id={LAYER.sites}
            type="symbol"
            layout={{
              "icon-image": ["get", "icon"],
              "icon-size": ["get", "size"],
              "icon-allow-overlap": true,
              "icon-ignore-placement": true,
            }}
          />
        </Source>

        {pulseAt && (
          <Source
            id={PULSE_SOURCE}
            type="geojson"
            data={collection([
              {
                type: "Feature" as const,
                properties: { pulse: 0, color: pulseColor },
                geometry: point(pulseAt),
              },
            ])}
          >
            <Layer
              id={LAYER.pulse}
              type="circle"
              paint={{
                "circle-radius": ["+", 9, ["*", ["get", "pulse"], 10]],
                "circle-color": "rgba(0, 0, 0, 0)",
                "circle-stroke-width": 2.2,
                "circle-stroke-color": ["get", "color"],
                "circle-stroke-opacity": ["-", 1, ["*", ["get", "pulse"], 0.65]],
              }}
            />
          </Source>
        )}

        {measureMode && <MeasureTool key={measureMode} mode={measureMode} onExit={exitMeasure} />}
        <AttributionControl position="bottom-left" compact />
      </Map>

      {box && (
        <div
          aria-hidden
          className="pointer-events-none absolute border border-sky-400 bg-sky-400/15"
          style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
        />
      )}

      {/* Top left: the focused entity, then one legend per colour layer. */}
      <div className="pointer-events-none absolute top-2 left-2 z-10 flex max-w-[60%] flex-col items-start gap-1.5">
        {mapFocus && (
          <div className="bg-surface-800/95 text-surface-100 pointer-events-auto flex max-w-full items-center gap-1 rounded border border-sky-400/60 py-0.5 pr-0.5 pl-1.5 text-[11px] shadow-lg">
            <LuMapPin size={12} className="shrink-0 text-sky-400" />
            <span className="truncate font-mono" title={mapFocus.entity}>
              {mapFocus.entity}
            </span>
            <button
              type="button"
              onClick={() => setMapFocus(null)}
              aria-label="Clear map focus"
              title="Back to this level's view"
              className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 focus-visible:ring-accent-500 rounded p-0.5 outline-none focus-visible:ring-1"
            >
              <LuX size={12} />
            </button>
          </div>
        )}
        {legends.map((spec) => (
          <MapLegend key={spec.name} spec={spec} />
        ))}
      </div>

      <Toolbar.Root
        orientation="vertical"
        aria-label="Map controls"
        className={`absolute top-2 right-2 z-10 flex w-9 flex-col items-center gap-0.5 p-0.5 ${PANEL_CLASS}`}
      >
        <MapLayersPopover withResults={withResults} />
        <div className="bg-surface-600 my-0.5 h-px w-full" />
        <ToolbarIconButton icon={LuPlus} label="Zoom in" onClick={() => zoomBy(1)} />
        <ToolbarIconButton icon={LuMinus} label="Zoom out" onClick={() => zoomBy(-1)} />
        <ToolbarIconButton
          icon={LuFrame}
          label={frameLabel}
          active={isManual || Boolean(mapFocus)}
          onClick={onFrame}
        />
        <ToolbarIconButton
          icon={LuCompass}
          label="Rotate north"
          onClick={() => mapRef.current?.getMap().resetNorthPitch({ duration: 300 })}
          disabled={!rotated}
        />
      </Toolbar.Root>

      <Toolbar.Root
        aria-label="Map tools"
        className={`absolute right-2 bottom-2 z-10 flex items-center gap-0.5 p-0.5 ${PANEL_CLASS}`}
      >
        <ToolbarIconButton
          icon={LuSquareDashedMousePointer}
          label={
            layers.isSelecting
              ? "Select locations: on (drag a box; Shift+drag adds, Ctrl/⌘+click toggles one)"
              : "Select locations (Shift+drag adds, Ctrl/⌘+click toggles one)"
          }
          active={layers.isSelecting}
          onClick={() => layers.setSelecting(!layers.isSelecting)}
        />
        <div aria-hidden className="bg-surface-600 h-4 w-px" />
        <ToolbarModeMenu
          label="Basemap"
          options={BASEMAP_OPTIONS}
          value={basemap}
          onChange={setBasemap}
          triggerIcon={LuEarth}
        />
        <ToolbarModeMenu
          label="Measure"
          options={MEASURE_OPTIONS}
          value={activeTool}
          onChange={setActiveTool}
          active={measureMode !== null}
          triggerIcon={measureMode ? undefined : LuRuler}
        />
      </Toolbar.Root>

      {/* Bottom left: what the level highlights. */}
      {highlight && buses && (
        <div className="bg-surface-900/80 text-surface-300 pointer-events-none absolute bottom-2 left-9 z-10 flex max-w-[55%] flex-col gap-0.5 rounded px-1.5 py-1 text-[10px] leading-tight">
          <span>
            <b className="text-surface-100">{highlight.buses.size.toLocaleString()}</b> of{" "}
            {buses.length.toLocaleString()} buses
            {ends.size > 0 && `, ${ends.size.toLocaleString()} line ends`}
          </span>
          <span>
            <b className="text-surface-100">{litLines.toLocaleString()}</b> of{" "}
            {lines.length.toLocaleString()} lines
          </span>
          {sites !== null && (
            <span>
              <b className="text-surface-100">{located.toLocaleString()}</b> of{" "}
              {memberCount.toLocaleString()} entities have their own location
              {located > 0 &&
                (layers.showSiting ? "; dashed lines join them to their bus" : "; siting hidden")}
            </span>
          )}
        </div>
      )}

      {busesData.status === "error" && (
        <div className="border-danger-500/50 bg-surface-800/95 text-surface-100 absolute inset-x-0 top-12 z-10 mx-auto w-fit rounded border px-3 py-1.5 text-[12px] shadow-lg">
          Can't read the record's buses.
        </div>
      )}
      {showOverlay && (
        <div
          role="status"
          aria-label="Loading the map"
          onTransitionEnd={() => setShowOverlay(false)}
          className={`pointer-events-none absolute inset-0 z-10 transition-opacity duration-500 ${isLoaded && buses ? "opacity-0" : "opacity-100"}`}
        >
          <MapLoadingOverlay />
        </div>
      )}
    </div>
  );
}
