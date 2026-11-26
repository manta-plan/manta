import { describe, expect, it } from "vitest";
import { computeCrop, rectFromPoints } from "./capture-region";

describe("rectFromPoints", () => {
  it("normalises a drag in any direction", () => {
    expect(rectFromPoints({ x: 50, y: 40 }, { x: 10, y: 20 })).toEqual({
      x: 10,
      y: 20,
      width: 40,
      height: 20,
    });
  });
});

describe("computeCrop", () => {
  it("scales the selection to canvas pixels", () => {
    expect(computeCrop({ x: 10, y: 20, width: 100, height: 50 }, { x: 0, y: 0 }, 2)).toEqual({
      x: 20,
      y: 40,
      width: 200,
      height: 100,
    });
  });

  it("offsets by the scrolled page origin", () => {
    expect(computeCrop({ x: 10, y: 20, width: 30, height: 30 }, { x: 0, y: -100 }, 1)).toEqual({
      x: 10,
      y: 120,
      width: 30,
      height: 30,
    });
  });
});
