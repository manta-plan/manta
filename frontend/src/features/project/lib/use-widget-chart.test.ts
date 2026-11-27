import { describe, expect, it } from "vitest";
import { graphic } from "echarts";
import { ZOOM_HANDLE_HEIGHT, ZOOM_HANDLE_ICON, timeZoom } from "./use-widget-chart";

const colors = {
  text: "#a0b6ca",
  axisLine: "#2c4763",
  splitLine: "#16253a",
  tooltipBackground: "#0b1522",
  strongText: "#e6eef6",
};

describe("timeZoom", () => {
  it("has no slider for short series", () => {
    expect(timeZoom(colors, 48)).toEqual({ gridBottom: 8 });
  });

  it("gives long series a slider with large handles and a hover state", () => {
    const { dataZoom, gridBottom } = timeZoom(colors, 49);
    const slider = (dataZoom as Record<string, unknown>[])[1];
    expect(slider).toMatchObject({
      type: "slider",
      handleIcon: ZOOM_HANDLE_ICON,
      handleSize: ZOOM_HANDLE_HEIGHT,
      emphasis: { handleStyle: { color: "#5699ff" } },
    });
    // The plot leaves room for the taller slider.
    expect(gridBottom).toBeGreaterThanOrEqual(ZOOM_HANDLE_HEIGHT + 6);
  });

  it("grabs a handle in a 28x40 box, wider than the drawn grip", () => {
    // echarts fits the icon to the handle's height, keeping its aspect, and
    // hit-tests a handle by its bounding box (rectHover).
    const square = { x: 0, y: 0, width: ZOOM_HANDLE_HEIGHT, height: ZOOM_HANDLE_HEIGHT };
    const box = graphic
      .makePath(ZOOM_HANDLE_ICON.slice("path://".length), {}, square, "center")
      .getBoundingRect();
    expect(box.height).toBeCloseTo(40);
    expect(box.width).toBeCloseTo(28);
  });
});
