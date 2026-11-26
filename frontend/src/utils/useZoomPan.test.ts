import { describe, expect, it } from "vitest";
import { IDENTITY_VIEW, clampView, zoomAround } from "./useZoomPan";

const box = { width: 200, height: 100 };

describe("clampView", () => {
  it("keeps the fitted view where it is", () => {
    expect(clampView(IDENTITY_VIEW, box)).toEqual(IDENTITY_VIEW);
  });

  it("stops the content leaving a gap on the left or top", () => {
    expect(clampView({ scale: 2, x: 50, y: 30 }, box)).toEqual({ scale: 2, x: 0, y: 0 });
  });

  it("stops the content leaving a gap on the right or bottom", () => {
    expect(clampView({ scale: 2, x: -500, y: -500 }, box)).toEqual({
      scale: 2,
      x: -200,
      y: -100,
    });
  });
});

describe("zoomAround", () => {
  it("keeps the point under the cursor still", () => {
    const next = zoomAround(IDENTITY_VIEW, 2, 50, 25, box);
    expect(next).toEqual({ scale: 2, x: -50, y: -25 });
    // Content point (50, 25) maps back to the same box point.
    expect(50 * next.scale + next.x).toBe(50);
    expect(25 * next.scale + next.y).toBe(25);
  });

  it("returns to the fitted view when zoomed back to 1", () => {
    const zoomed = zoomAround(IDENTITY_VIEW, 3, 120, 60, box);
    expect(zoomAround(zoomed, 1, 10, 10, box)).toEqual(IDENTITY_VIEW);
  });
});
