// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { StyleSpecification } from "maplibre-gl";
import type { BasemapId } from "../../../project/store/types";

// Basemaps (CARTO vector, Esri imagery) and the map's own colours.

export const BASEMAP_STYLE: Record<BasemapId, string | StyleSpecification> = {
  "vector-dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  "vector-light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  satellite: {
    version: 8,
    // CARTO's glyphs, so labels still have fonts.
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

export const COLORS = {
  accent: "#2c73ff",
  accentLight: "#5699ff",
  /** The selection and focus colour (--halo). */
  halo: "#38bdf8",
  muted: "#64748b",
  farEnd: "#cbd5e1",
  line: "#94a3b8",
};

/** A diamond marker image id for a colour; drawn on demand (styleimagemissing). */
export const diamondIcon = (color: string) => `site-diamond:${color}`;

export function drawDiamond(
  id: string,
): { width: number; height: number; data: Uint8Array } | null {
  if (!id.startsWith("site-diamond:")) return null;
  const color = id.slice("site-diamond:".length);
  const size = 32;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.beginPath();
  context.moveTo(size / 2, 3);
  context.lineTo(size - 3, size / 2);
  context.lineTo(size / 2, size - 3);
  context.lineTo(3, size / 2);
  context.closePath();
  context.fillStyle = color;
  context.fill();
  context.lineWidth = 2.5;
  context.strokeStyle = "rgba(10, 13, 18, 0.85)";
  context.stroke();
  return {
    width: size,
    height: size,
    data: new Uint8Array(context.getImageData(0, 0, size, size).data.buffer),
  };
}
