import { describe, expect, it } from "vitest";
import { drawAnnotations, strokeWidthFor } from "./draw-annotations";

/** Records the path and paint calls a canvas context receives. */
function fakeContext() {
  const calls: string[] = [];
  const ctx = {
    lineWidth: 0,
    lineJoin: "",
    fillStyle: "",
    strokeStyle: "",
    globalAlpha: 1,
    save: () => calls.push("save"),
    restore: () => calls.push("restore"),
    beginPath: () => calls.push("beginPath"),
    closePath: () => calls.push("closePath"),
    rect: (x: number, y: number, w: number, h: number) => calls.push(`rect ${x} ${y} ${w} ${h}`),
    moveTo: (x: number, y: number) => calls.push(`moveTo ${x} ${y}`),
    lineTo: (x: number, y: number) => calls.push(`lineTo ${x} ${y}`),
    fill: () => calls.push(`fill ${ctx.fillStyle} ${ctx.globalAlpha}`),
    stroke: () => calls.push(`stroke ${ctx.strokeStyle} ${ctx.globalAlpha} ${ctx.lineWidth}`),
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, calls };
}

describe("strokeWidthFor", () => {
  it("never goes below 3 px", () => {
    expect(strokeWidthFor(400)).toBe(3);
  });

  it("grows with the image", () => {
    expect(strokeWidthFor(2560)).toBe(6);
  });
});

describe("drawAnnotations", () => {
  it("fills faintly and outlines a rectangle in its colour", () => {
    const { ctx, calls } = fakeContext();
    drawAnnotations(ctx, [{ type: "RECTANGLE", color: "#ef4444", x: 1, y: 2, w: 30, h: 40 }], 800);
    expect(calls).toEqual([
      "save",
      "beginPath",
      "rect 1 2 30 40",
      "fill #ef4444 0.15",
      "stroke #ef4444 1 3",
      "restore",
    ]);
  });

  it("closes a polygon through its points", () => {
    const { ctx, calls } = fakeContext();
    drawAnnotations(
      ctx,
      [
        {
          type: "POLYGON",
          color: "#3b82f6",
          points: [
            [0, 0],
            [10, 0],
            [5, 8],
          ],
        },
      ],
      800,
    );
    expect(calls.slice(1, 7)).toEqual([
      "beginPath",
      "moveTo 0 0",
      "lineTo 10 0",
      "lineTo 5 8",
      "closePath",
      "fill #3b82f6 0.15",
    ]);
  });

  it("skips a polygon with fewer than two points", () => {
    const { ctx, calls } = fakeContext();
    drawAnnotations(ctx, [{ type: "POLYGON", color: "#fff", points: [[1, 1]] }], 800);
    expect(calls).toEqual(["save", "beginPath", "restore"]);
  });
});
