// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

// Annotorious draws its shapes as an SVG overlay, so the exported PNG needs
// them painted onto the screenshot itself.

export type AnnotationShape =
  | { type: "RECTANGLE"; color: string; x: number; y: number; w: number; h: number }
  | { type: "POLYGON"; color: string; points: number[][] };

/** Fill alpha for the inside of a shape; the outline is opaque. */
export const FILL_ALPHA = 0.15;

/** Outline width in image pixels, so it reads the same on any screenshot size. */
export function strokeWidthFor(imageWidth: number): number {
  return Math.max(3, Math.round(imageWidth / 400));
}

/** Draw the shapes, in image pixel coordinates, onto a canvas context. */
export function drawAnnotations(
  ctx: CanvasRenderingContext2D,
  shapes: AnnotationShape[],
  imageWidth: number,
): void {
  ctx.save();
  ctx.lineWidth = strokeWidthFor(imageWidth);
  ctx.lineJoin = "round";
  for (const shape of shapes) {
    ctx.beginPath();
    if (shape.type === "RECTANGLE") {
      ctx.rect(shape.x, shape.y, shape.w, shape.h);
    } else {
      if (shape.points.length < 2) continue;
      shape.points.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
      ctx.closePath();
    }
    ctx.fillStyle = shape.color;
    ctx.globalAlpha = FILL_ALPHA;
    ctx.fill();
    ctx.strokeStyle = shape.color;
    ctx.globalAlpha = 1;
    ctx.stroke();
  }
  ctx.restore();
}
