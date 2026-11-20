import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, {
  AttributionControl,
  ScaleControl,
  Source,
  Layer,
  Popup,
  type MapLayerMouseEvent,
  type MapRef,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type {
  ExpressionSpecification,
  FilterSpecification,
  GeoJSONSource,
  StyleSpecification,
} from "maplibre-gl";
import { useProjectStore, type BasemapId } from "../store/project-store";
import { NODAL } from "../store/types";
import {
  branchFeatures,
  placeFeatures,
  placeLocations,
  regionFeatures,
  zoneOf,
  type BranchFeature,
} from "../lib/record-geo";
import { entityLabel } from "../lib/record-format";
import {
  LABELS_LAYER,
  LINES_LAYER,
  LOCATIONS_LAYER,
  REGIONS_LAYER,
  TRANSFORMERS_LAYER,
  isLayerVisible,
  layerStyle,
  linkLayerCarrier,
  mapLayerCategories,
  type MapLayerDef,
} from "../data/map-layers";
import { MapLoadingOverlay } from "./map-loading-overlay";
import { MeasureTool } from "./measure-tool";
import { MEASURE_LAYER_IDS, type MeasureMode } from "../lib/measure";
import { LocationPopupGraph } from "./location-view";

const REGION_FILL_LAYER_ID = "regions-fill";
const PLACE_LAYER_ID = "places-point";
const PLACE_LABEL_LAYER_ID = "places-label";
const BRANCH_LAYER_PREFIX = "branches-";
const ACTIVE_CIRCLE_HIGHLIGHT_SOURCE_ID = "active-circle-highlight";
const ACTIVE_CIRCLE_HALO_LAYER_ID = "active-circle-highlight-halo";
const ACTIVE_CIRCLE_RING_LAYER_ID = "active-circle-highlight-ring";
const ACTIVE_LINE_HALO_LAYER_ID = "active-line-highlight-halo";
const ACTIVE_LINE_STROKE_LAYER_ID = "active-line-highlight-stroke";

const TOP_RENDERED_LAYER_IDS = [
  ACTIVE_LINE_HALO_LAYER_ID,
  ACTIVE_LINE_STROKE_LAYER_ID,
  ACTIVE_CIRCLE_HALO_LAYER_ID,
  ACTIVE_CIRCLE_RING_LAYER_ID,
  PLACE_LAYER_ID,
  PLACE_LABEL_LAYER_ID,
  ...MEASURE_LAYER_IDS,
];

// Zones get a color each, cycling through this palette.
const ZONE_PALETTE = [
  "#2c73ff",
  "#14b8a6",
  "#f59e0b",
  "#a855f7",
  "#ef4444",
  "#22c55e",
  "#ec4899",
  "#06b6d4",
  "#eab308",
  "#8b5cf6",
];

const BASEMAP_STYLE: Record<BasemapId, string | StyleSpecification> = {
  "vector-dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  "vector-light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  satellite: {
    version: 8,
    // Reuse CARTO's glyphs so the label symbol layer still has fonts.
    glyphs: "https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf",
    sources: {
      "esri-world-imagery": {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        maxzoom: 19,
        attribution:
          "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
      },
    },
    layers: [{ id: "esri-world-imagery", type: "raster", source: "esri-world-imagery" }],
  },
};

// A selected place adds this on top of the user's fill opacity (capped at
// fully opaque) and thickens its outline, so it still stands out when the
// fill has been turned up — e.g. over satellite imagery.
const SELECTED_AREA_FILL_BOOST = 0.12;
const SELECTED_AREA_OUTLINE_EXTRA_WIDTH = 1.2;

function areaFillOpacity(opacity: number, selectedName: string | null): ExpressionSpecification {
  return [
    "min",
    1,
    [
      "+",
      opacity,
      ["case", ["==", ["get", "name"], selectedName ?? ""], SELECTED_AREA_FILL_BOOST, 0],
    ],
  ];
}

function areaOutlineWidth(width: number, selectedName: string | null): ExpressionSpecification {
  return [
    "case",
    ["==", ["get", "name"], selectedName ?? ""],
    width + SELECTED_AREA_OUTLINE_EXTRA_WIDTH,
    width,
  ];
}

// Which branches a line layer draws.
function branchFilter(layer: MapLayerDef): FilterSpecification {
  if (layer.id === LINES_LAYER) return ["==", ["get", "ctype"], "Line"];
  if (layer.id === TRANSFORMERS_LAYER) return ["==", ["get", "ctype"], "Transformer"];
  return [
    "all",
    ["==", ["get", "ctype"], "Link"],
    ["==", ["get", "carrier"], linkLayerCarrier(layer.id) ?? ""],
  ];
}

interface PlacePopupInfo {
  longitude: number;
  latitude: number;
  name: string;
}

// The item drawer's width (w-72), over the map's left edge.
const ITEM_DRAWER_WIDTH = 288;

interface BranchPopupInfo {
  longitude: number;
  latitude: number;
  branch: BranchFeature;
}

export function MapView({ isVisible = true }: { isVisible?: boolean }) {
  const viewState = useProjectStore((s) => s.viewState);
  const setViewState = useProjectStore((s) => s.setViewState);
  const setCursorPosition = useProjectStore((s) => s.setCursorPosition);
  const basemap = useProjectStore((s) => s.basemap);
  const activeTool = useProjectStore((s) => s.activeTool);
  const setActiveTool = useProjectStore((s) => s.setActiveTool);
  const record = useProjectStore((s) => s.record);
  const recordStatus = useProjectStore((s) => s.recordStatus);
  const recordError = useProjectStore((s) => s.recordError);
  const reconnect = useProjectStore((s) => s.reconnect);
  const resolution = useProjectStore((s) => s.resolution);
  const selectedItem = useProjectStore((s) => s.selectedItem);
  const selectItem = useProjectStore((s) => s.selectItem);
  const openItemDrawer = useProjectStore((s) => s.openItemDrawer);
  const openLocationView = useProjectStore((s) => s.openLocationView);
  const mapLayerVisibility = useProjectStore((s) => s.mapLayerVisibility);
  const mapLayerStyle = useProjectStore((s) => s.mapLayerStyle);
  const mapFocus = useProjectStore((s) => s.mapFocus);

  const [placePopup, setPlacePopup] = useState<PlacePopupInfo | null>(null);
  const [branchPopup, setBranchPopup] = useState<BranchPopupInfo | null>(null);
  const [selectedPlace, setSelectedPlace] = useState<string | null>(null);
  const [isHoveringInteractive, setIsHoveringInteractive] = useState(false);
  const [isMapLoaded, setIsMapLoaded] = useState(false);
  const [showLoadingOverlay, setShowLoadingOverlay] = useState(true);
  const mapRef = useRef<MapRef>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // The map stays mounted across project tab switches so loaded tiles and
  // style state survive. Keep its canvas aligned with the containing panel.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => mapRef.current?.resize());
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setPlacePopup(null);
    setBranchPopup(null);
    setSelectedPlace(null);
  }, [resolution]);

  const measureMode: MeasureMode | null =
    activeTool === "measure-distance" ? "distance" : activeTool === "measure-area" ? "area" : null;
  const exitMeasureTool = useCallback(() => setActiveTool("select"), [setActiveTool]);

  // The map stays mounted behind other project tabs, whose toolbars have no
  // way to turn the measure tool off — so leaving the map ends it.
  useEffect(() => {
    if (!isVisible) exitMeasureTool();
  }, [exitMeasureTool, isVisible]);

  const zonal = resolution !== NODAL;
  const zones = useMemo(
    () => (record ? zoneOf(record, resolution) : new globalThis.Map<string, string>()),
    [record, resolution],
  );
  const zoneColor = useMemo(() => {
    const names = [...new Set(zones.values())].sort();
    return new globalThis.Map(
      names.map((name, index) => [name, ZONE_PALETTE[index % ZONE_PALETTE.length]]),
    );
  }, [zones]);

  const layers = useMemo(() => {
    const linkCarriers = [
      ...new Set(
        record?.branches
          .filter((branch) => branch.ctype === "Link")
          .map((branch) => branch.carrier ?? "") ?? [],
      ),
    ]
      .sort()
      .map((carrier) => ({
        carrier,
        label: record?.carriers[carrier]?.niceName || carrier,
        color: record?.carriers[carrier]?.color ?? "#94a3b8",
      }));
    return new globalThis.Map(
      mapLayerCategories(linkCarriers, zonal)
        .flatMap((category) => category.layers)
        .map((layer) => [layer.id, layer]),
    );
  }, [record, zonal]);
  const visible = (id: string) => {
    const layer = layers.get(id);
    return Boolean(layer && isLayerVisible(mapLayerVisibility, layer));
  };
  const style = (id: string) => layerStyle(mapLayerStyle, layers.get(id) as MapLayerDef);
  const branchLayers = [...layers.values()].filter(
    (layer) => layer.geometry === "line" && visible(layer.id),
  );

  const regions = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: regionFeatures(record, resolution).map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          color: feature.properties.zone
            ? (zoneColor.get(feature.properties.zone) ?? ZONE_PALETTE[0])
            : "",
        },
      })),
    }),
    [record, resolution, zoneColor],
  );
  const places = useMemo(
    () => (record ? placeFeatures(record, resolution) : []),
    [record, resolution],
  );
  const branches = useMemo(
    () => (record ? branchFeatures(record, resolution) : []),
    [record, resolution],
  );
  const placeByName = useMemo(
    () => new globalThis.Map(places.map((place) => [place.properties.name, place])),
    [places],
  );

  // The selected entity on the map: its branch lines, or a pulse at its place.
  const activeBranches = useMemo(() => {
    if (selectedItem?.kind !== "entity") return null;
    const features = branches.filter((branch) =>
      branch.properties.entities.includes(selectedItem.entity),
    );
    return features.length > 0 ? { type: "FeatureCollection" as const, features } : null;
  }, [branches, selectedItem]);
  const activeCircleHighlight = useMemo(() => {
    if (selectedItem?.kind !== "entity" || activeBranches) return null;
    const location = selectedItem.locations[0];
    const place = location ? placeByName.get(zones.get(location) ?? location) : undefined;
    if (!place) return null;
    return {
      type: "FeatureCollection" as const,
      features: [
        {
          type: "Feature" as const,
          properties: {
            color: record?.carriers[selectedItem.carrier ?? ""]?.color ?? "#2c73ff",
            baseRadius: 8,
            pulse: 0,
          },
          geometry: place.geometry,
        },
      ],
    };
  }, [activeBranches, placeByName, record, selectedItem, zones]);

  useEffect(() => {
    if (!isMapLoaded || !activeCircleHighlight) return;

    let animationFrame = 0;
    const startedAt = performance.now();
    const animate = (now: number) => {
      const source = mapRef.current?.getMap().getSource(ACTIVE_CIRCLE_HIGHLIGHT_SOURCE_ID) as
        | GeoJSONSource
        | undefined;
      if (!source) {
        animationFrame = requestAnimationFrame(animate);
        return;
      }

      const pulse = ((now - startedAt) % 1200) / 1200;
      source.setData({
        ...activeCircleHighlight,
        features: activeCircleHighlight.features.map((feature) => ({
          ...feature,
          properties: { ...feature.properties, pulse },
        })),
      });
      animationFrame = requestAnimationFrame(animate);
    };

    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [activeCircleHighlight, isMapLoaded]);

  useEffect(() => {
    if (!isMapLoaded || !isVisible) return;

    const animationFrame = requestAnimationFrame(() => {
      const map = mapRef.current?.getMap();
      if (!map) return;

      for (const layerId of TOP_RENDERED_LAYER_IDS) {
        if (map.getLayer(layerId)) map.moveLayer(layerId);
      }
    });

    return () => cancelAnimationFrame(animationFrame);
  }, [
    activeCircleHighlight,
    activeBranches,
    places,
    branchLayers.length,
    isMapLoaded,
    isVisible,
    resolution,
  ]);

  // Show the points asked for, clear of the item drawer over the map's left edge.
  useEffect(() => {
    const map = mapRef.current;
    if (!isMapLoaded || !map || !mapFocus || mapFocus.points.length === 0) return;
    const padding = { top: 60, bottom: 60, left: ITEM_DRAWER_WIDTH + 60, right: 60 };
    const [first, ...rest] = mapFocus.points;
    if (rest.length === 0) {
      map.flyTo({ center: first, zoom: Math.max(map.getZoom(), 8), padding, duration: 800 });
      return;
    }
    const lngs = mapFocus.points.map(([lng]) => lng);
    const lats = mapFocus.points.map(([, lat]) => lat);
    map.fitBounds(
      [
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ],
      { padding, maxZoom: 10, duration: 800 },
    );
  }, [isMapLoaded, mapFocus]);

  const handleMouseMove = (e: MapLayerMouseEvent) => {
    setCursorPosition({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    setIsHoveringInteractive((e.features?.length ?? 0) > 0);
  };

  const openPlace = (name: string, coordinates: [number, number]) => {
    setBranchPopup(null);
    setSelectedPlace(name);
    setPlacePopup({ longitude: coordinates[0], latitude: coordinates[1], name });
  };

  const handleClick = (e: MapLayerMouseEvent) => {
    if (measureMode) return;
    const feature = e.features?.[0];
    const layerId = feature?.layer?.id ?? "";
    if (layerId === PLACE_LAYER_ID && feature?.geometry.type === "Point") {
      const [longitude, latitude] = feature.geometry.coordinates;
      openPlace(String(feature.properties?.name ?? ""), [longitude, latitude]);
      return;
    }
    if (layerId.startsWith(BRANCH_LAYER_PREFIX)) {
      const branch = branches.find((item) => item.properties.id === feature?.properties?.id);
      if (branch) {
        setPlacePopup(null);
        setBranchPopup({ longitude: e.lngLat.lng, latitude: e.lngLat.lat, branch });
        const [entity] = branch.properties.entities;
        const found = record?.branches.find((item) => item.entity === entity);
        if (entity && found)
          selectItem({
            kind: "entity",
            entity,
            ctype: found.ctype,
            carrier: found.carrier,
            locations: [found.location0, found.location1],
          });
      }
      return;
    }
    if (layerId === REGION_FILL_LAYER_ID) {
      const name = String(feature?.properties?.name ?? "");
      const place = placeByName.get(name);
      if (place) openPlace(name, place.geometry.coordinates);
      return;
    }
    setPlacePopup(null);
    setBranchPopup(null);
    setSelectedPlace(null);
  };

  const popupLocations = useMemo(
    () => (placePopup && record ? placeLocations(record, resolution, placePopup.name) : []),
    [placePopup, record, resolution],
  );
  const placeTitle = (name: string) => (zonal ? `Zone ${name}` : `Location ${name}`);
  const lineColor = (layer: MapLayerDef) => style(layer.id).color;

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <Map
        ref={mapRef}
        {...viewState}
        onLoad={() => setIsMapLoaded(true)}
        onMove={(evt) => setViewState(evt.viewState)}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => {
          setCursorPosition(null);
          setIsHoveringInteractive(false);
        }}
        onClick={handleClick}
        doubleClickZoom={!measureMode}
        interactiveLayerIds={
          measureMode
            ? []
            : [
                ...(visible(REGIONS_LAYER) ? [REGION_FILL_LAYER_ID] : []),
                ...branchLayers.map((layer) => `${BRANCH_LAYER_PREFIX}${layer.id}`),
                ...(visible(LOCATIONS_LAYER) ? [PLACE_LAYER_ID] : []),
              ]
        }
        cursor={measureMode ? "crosshair" : isHoveringInteractive ? "pointer" : undefined}
        mapStyle={BASEMAP_STYLE[basemap]}
        attributionControl={false}
        style={{ width: "100%", height: "100%" }}
      >
        {visible(REGIONS_LAYER) && (
          <Source id="regions" type="geojson" data={regions}>
            <Layer
              id={REGION_FILL_LAYER_ID}
              type="fill"
              paint={{
                "fill-color": zonal ? ["get", "color"] : style(REGIONS_LAYER).color,
                "fill-opacity": areaFillOpacity(
                  zonal
                    ? Math.max(style(REGIONS_LAYER).opacity, 0.22)
                    : style(REGIONS_LAYER).opacity,
                  selectedPlace,
                ),
              }}
            />
            <Layer
              id="regions-outline"
              type="line"
              paint={{
                "line-color": zonal ? ["get", "color"] : style(REGIONS_LAYER).color,
                "line-width": areaOutlineWidth(zonal ? 1.2 : 0.9, selectedPlace),
              }}
            />
          </Source>
        )}

        {branchLayers.length > 0 && (
          <Source
            id="branches"
            type="geojson"
            data={{ type: "FeatureCollection", features: branches }}
          >
            {branchLayers.map((layer) => (
              <Layer
                key={layer.id}
                id={`${BRANCH_LAYER_PREFIX}${layer.id}`}
                type="line"
                filter={branchFilter(layer)}
                layout={{ "line-cap": "round" }}
                paint={{
                  "line-color": lineColor(layer),
                  "line-width": ["interpolate", ["linear"], ["get", "count"], 1, 1.5, 10, 4, 40, 7],
                  "line-opacity": style(layer.id).opacity,
                }}
              />
            ))}
          </Source>
        )}

        {activeBranches && (
          <Source id="active-line-highlight" type="geojson" data={activeBranches}>
            <Layer
              id={ACTIVE_LINE_HALO_LAYER_ID}
              type="line"
              paint={{
                "line-color": "#38bdf8",
                "line-width": 10,
                "line-opacity": 0.24,
                "line-blur": 1.5,
              }}
            />
            <Layer
              id={ACTIVE_LINE_STROKE_LAYER_ID}
              type="line"
              paint={{ "line-color": "#38bdf8", "line-width": 3.5, "line-opacity": 0.95 }}
            />
          </Source>
        )}

        {activeCircleHighlight && (
          <Source
            id={ACTIVE_CIRCLE_HIGHLIGHT_SOURCE_ID}
            type="geojson"
            data={activeCircleHighlight}
          >
            <Layer
              id={ACTIVE_CIRCLE_HALO_LAYER_ID}
              type="circle"
              paint={{
                "circle-radius": ["+", ["get", "baseRadius"], ["*", ["get", "pulse"], 16]],
                "circle-color": ["get", "color"],
                "circle-opacity": ["-", 0.28, ["*", ["get", "pulse"], 0.24]],
                "circle-blur": 0.2,
              }}
            />
            <Layer
              id={ACTIVE_CIRCLE_RING_LAYER_ID}
              type="circle"
              paint={{
                "circle-radius": ["+", ["get", "baseRadius"], 4],
                "circle-color": "rgba(0, 0, 0, 0)",
                "circle-stroke-width": 2,
                "circle-stroke-color": ["get", "color"],
                "circle-stroke-opacity": 0.95,
              }}
            />
          </Source>
        )}

        {(visible(LOCATIONS_LAYER) || visible(LABELS_LAYER)) && (
          <Source id="places" type="geojson" data={{ type: "FeatureCollection", features: places }}>
            {visible(LOCATIONS_LAYER) && (
              <Layer
                id={PLACE_LAYER_ID}
                type="circle"
                paint={{
                  "circle-radius": [
                    "+",
                    ["case", ["==", ["get", "name"], selectedPlace ?? ""], 2, 0],
                    zonal
                      ? ["interpolate", ["linear"], ["get", "locations"], 1, 6, 30, 12]
                      : ["interpolate", ["linear"], ["get", "buses"], 1, 3.5, 17, 6.5],
                  ],
                  "circle-color": style(LOCATIONS_LAYER).color,
                  "circle-stroke-width": 1.5,
                  "circle-stroke-color": basemap === "vector-light" ? "#ffffff" : "#0a0d12",
                  "circle-opacity": style(LOCATIONS_LAYER).opacity,
                }}
              />
            )}
            {visible(LABELS_LAYER) && (
              <Layer
                id={PLACE_LABEL_LAYER_ID}
                type="symbol"
                minzoom={zonal ? 0 : 8.5}
                layout={{
                  "text-field": ["get", "name"],
                  "text-size": 11,
                  "text-offset": [0, 1.1],
                  "text-anchor": "top",
                }}
                paint={{
                  // Imagery is dark and busy whatever the theme, so it takes the dark-map label colors.
                  "text-color": basemap === "vector-light" ? "#1f2937" : "#e5e7eb",
                  "text-halo-color": basemap === "vector-light" ? "#ffffff" : "#000000",
                  "text-halo-width": 1.5,
                  "text-opacity": style(LABELS_LAYER).opacity,
                }}
              />
            )}
          </Source>
        )}

        {placePopup && (
          <Popup
            longitude={placePopup.longitude}
            latitude={placePopup.latitude}
            onClose={() => {
              setPlacePopup(null);
              setSelectedPlace(null);
            }}
            closeButton
            closeOnClick={false}
            offset={12}
            maxWidth="none"
          >
            <LocationPopupGraph
              title={placeTitle(placePopup.name)}
              locations={popupLocations}
              onOpen={() => openLocationView(placeTitle(placePopup.name), popupLocations)}
            />
          </Popup>
        )}

        {branchPopup && (
          <Popup
            longitude={branchPopup.longitude}
            latitude={branchPopup.latitude}
            onClose={() => setBranchPopup(null)}
            closeButton
            closeOnClick={false}
            offset={8}
            maxWidth="320px"
          >
            <div className="flex flex-col gap-1 px-1 py-0.5">
              <div className="text-surface-50 pr-5 text-[12px] font-semibold">
                {branchPopup.branch.properties.ctype}
                {branchPopup.branch.properties.carrier &&
                  ` · ${record?.carriers[branchPopup.branch.properties.carrier]?.niceName || branchPopup.branch.properties.carrier}`}
                <span className="text-surface-400 ml-1 font-normal">
                  ×{branchPopup.branch.properties.count}
                </span>
              </div>
              <ul className="flex max-h-52 flex-col overflow-y-auto text-[11px]">
                {branchPopup.branch.properties.entities.map((entity) => {
                  const branch = record?.branches.find((item) => item.entity === entity);
                  return (
                    <li key={entity}>
                      <button
                        type="button"
                        title={entity}
                        onClick={() =>
                          branch &&
                          openItemDrawer({
                            kind: "entity",
                            entity,
                            ctype: branch.ctype,
                            carrier: branch.carrier,
                            locations: [branch.location0, branch.location1],
                          })
                        }
                        className="text-surface-200 hover:bg-surface-700 hover:text-surface-50 w-full truncate rounded px-1 py-0.5 text-left outline-none"
                      >
                        {entityLabel(entity, branch?.location0 ?? null)}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </Popup>
        )}

        {measureMode && (
          <MeasureTool key={measureMode} mode={measureMode} onExit={exitMeasureTool} />
        )}

        <ScaleControl position="bottom-left" unit="metric" />
        <AttributionControl position="bottom-left" compact />
      </Map>
      {recordStatus === "error" && (
        <div
          className="border-danger-500/50 bg-surface-800/90 text-surface-100 absolute top-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded border px-3 py-1.5 text-[12px] shadow-lg"
          title={recordError ?? undefined}
        >
          Can't reach the record server.
          <button
            type="button"
            onClick={reconnect}
            className="text-accent-400 cursor-pointer font-medium hover:underline"
          >
            Retry
          </button>
        </div>
      )}
      {showLoadingOverlay && (
        <div
          onTransitionEnd={() => setShowLoadingOverlay(false)}
          className={`absolute inset-0 z-10 transition-opacity duration-500 ${
            isMapLoaded && recordStatus !== "loading" && recordStatus !== "idle"
              ? "pointer-events-none opacity-0"
              : "opacity-100"
          }`}
        >
          <MapLoadingOverlay />
        </div>
      )}
    </div>
  );
}
