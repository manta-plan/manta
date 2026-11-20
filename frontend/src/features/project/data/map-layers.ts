// The map's layers. Most are fixed; links get one layer per carrier the record
// has between locations (H2 pipeline, gas pipeline, …), built from the data,
// so another record's carriers (DC, say) show up the same way.

export type MapLayerGeometry = "polygon" | "line" | "point";

export interface MapLayerStyle {
  color: string;
  opacity: number;
}

export interface MapLayerDef {
  id: string;
  label: string;
  description: string;
  geometry: MapLayerGeometry;
  color: string;
  // Whether one user-chosen color drives the layer's paint. Regions in zones
  // and labels color per feature, so a single override wouldn't apply.
  colorEditable: boolean;
  opacity: number;
  visible: boolean;
}

export interface MapLayerCategory {
  id: string;
  label: string;
  layers: MapLayerDef[];
}

export const REGIONS_LAYER = "regions";
export const LOCATIONS_LAYER = "locations";
export const LINES_LAYER = "lines";
export const TRANSFORMERS_LAYER = "transformers";
export const LABELS_LAYER = "location-labels";
const LINK_LAYER_PREFIX = "links:";

export function linkLayerId(carrier: string): string {
  return `${LINK_LAYER_PREFIX}${carrier}`;
}

export function linkLayerCarrier(id: string): string | null {
  return id.startsWith(LINK_LAYER_PREFIX) ? id.slice(LINK_LAYER_PREFIX.length) : null;
}

export function mapLayerCategories(
  linkCarriers: { carrier: string; label: string; color: string }[],
  zonal: boolean,
): MapLayerCategory[] {
  const place = zonal ? "Zones" : "Locations";
  return [
    {
      id: "areas",
      label: "Areas",
      layers: [
        {
          id: REGIONS_LAYER,
          label: "Regions",
          description: zonal ? "Bus regions, tinted by zone" : "Bus regions (Shape entities)",
          geometry: "polygon",
          color: "#2c73ff",
          colorEditable: !zonal,
          opacity: 0.12,
          visible: true,
        },
      ],
    },
    {
      id: "network",
      label: "Network",
      layers: [
        {
          id: LOCATIONS_LAYER,
          label: place,
          description: zonal
            ? "Zones, at the center of their locations"
            : "Locations: the buses of every carrier at one site",
          geometry: "point",
          color: "#2c73ff",
          colorEditable: true,
          opacity: 1,
          visible: true,
        },
        {
          id: LINES_LAYER,
          label: "Lines",
          description: `Lines between ${place.toLowerCase()}`,
          geometry: "line",
          color: "#94a3b8",
          colorEditable: true,
          opacity: 0.8,
          visible: true,
        },
        {
          id: TRANSFORMERS_LAYER,
          label: "Transformers",
          description: `Transformers between ${place.toLowerCase()}`,
          geometry: "line",
          color: "#f59e0b",
          colorEditable: true,
          opacity: 0.9,
          visible: true,
        },
      ],
    },
    ...(linkCarriers.length > 0
      ? [
          {
            id: "links",
            label: "Links",
            layers: linkCarriers.map(({ carrier, label, color }) => ({
              id: linkLayerId(carrier),
              label,
              description: `${label} links between ${place.toLowerCase()}`,
              geometry: "line" as const,
              color,
              colorEditable: true,
              opacity: 0.8,
              visible: false,
            })),
          },
        ]
      : []),
    {
      id: "labels",
      label: "Labels",
      layers: [
        {
          id: LABELS_LAYER,
          label: `${place} Labels`,
          description: `Names of ${place.toLowerCase()}`,
          geometry: "point",
          color: "#e5e7eb",
          colorEditable: false,
          opacity: 1,
          visible: true,
        },
      ],
    },
  ];
}

export function isLayerVisible(visibility: Record<string, boolean>, layer: MapLayerDef): boolean {
  return visibility[layer.id] ?? layer.visible;
}

export function layerStyle(
  styles: Record<string, Partial<MapLayerStyle>>,
  layer: MapLayerDef,
): MapLayerStyle {
  const override = styles[layer.id];
  return { color: override?.color ?? layer.color, opacity: override?.opacity ?? layer.opacity };
}
