import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { useAppStore } from "../../home/store";

// Shared look for the inspection widgets. Literal hex, not CSS vars —
// echarts paints to canvas (see ChartCard.tsx).

export const BAR_COLOR = "#5699ff";

export const CARRIER_COLORS: Record<string, string> = {
  "solar-pv-utility": "#f9d002",
  "solar-pv-rooftop": "#ffea80",
  "Onshore Wind": "#235ebc",
  "offwind-ac": "#6895dd",
  "offwind-dc": "#74c6f2",
  biomass: "#dd88cc",
  "run of river": "#3dbfb0",
  "electricity distribution grid": "#97ad8c",
  "H2 pipeline": "#f081dc",
  "land transport oil": "#aaaaaa",
  DC: "#8a1caf",
  AC: "#70af1d",
  nuclear: "#ff8c00",
  gas: "#e05b09",
  "H2 Electrolysis": "#ff29d9",
  "gas boiler": "#db6a25",
  "Fischer-Tropsch": "#3a4a1c",
  "heat pump": "#e6a55f",
  "hydro-phs": "#08ad97",
  "hydro-phs-pure": "#51dbcc",
  hydro: "#298c81",
  "Battery Storage": "#ace37f",
  "home battery": "#80c944",
  "H2 Store": "#bf13a0",
};

export function formatValue(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export function useChartColors() {
  const theme = useAppStore((s) => s.theme);
  return useMemo(
    () => ({
      text: theme === "dark" ? "#a0b6ca" : "#475569",
      axisLine: theme === "dark" ? "#2c4763" : "#cbd5e1",
      splitLine: theme === "dark" ? "#16253a" : "#f1f5f9",
      tooltipBackground: theme === "dark" ? "#0b1522" : "#ffffff",
      strongText: theme === "dark" ? "#e6eef6" : "#0f172a",
    }),
    [theme],
  );
}

type ChartColors = ReturnType<typeof useChartColors>;

const ZOOM_ACCENT = "#5699ff";

/**
 * The zoom slider's end handles: a grip 12px wide and 34px tall, drawn in a
 * 28x40 box. The two lone points (0,0 and 28,40) draw nothing but set the
 * box, and echarts hit-tests a handle by its box, so the grab area is
 * 28x40px, wider than the grip. Sized by ZOOM_HANDLE_HEIGHT (px).
 */
export const ZOOM_HANDLE_ICON =
  "path://M0,0M28,40" +
  "M8,6a3,3 0 0 1 3,-3h6a3,3 0 0 1 3,3v28a3,3 0 0 1 -3,3h-6a3,3 0 0 1 -3,-3Z" +
  "M12,14V26M16,14V26";
export const ZOOM_HANDLE_HEIGHT = 40;
const ZOOM_SLIDER_HEIGHT = 32;
const ZOOM_SLIDER_BOTTOM = 6;

/**
 * A time series' zoom: a slider under the chart, and dragging the plot to
 * pan. The wheel zooms only with Ctrl/Cmd held, so it still scrolls the page.
 * Only for series longer than two days of hourly snapshots; `gridBottom` is
 * the room the slider needs under the plot.
 */
export function timeZoom(
  colors: ChartColors,
  count: number,
): { dataZoom?: EChartsOption["dataZoom"]; gridBottom: number } {
  if (count <= 48) return { gridBottom: 8 };
  return {
    // The handles stand out past the slider by half their extra height; keep
    // the plot 12px clear of them.
    gridBottom: ZOOM_SLIDER_BOTTOM + (ZOOM_SLIDER_HEIGHT + ZOOM_HANDLE_HEIGHT) / 2 + 12,
    dataZoom: [
      { type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false, moveOnMouseMove: true },
      {
        type: "slider",
        height: ZOOM_SLIDER_HEIGHT,
        bottom: ZOOM_SLIDER_BOTTOM,
        borderColor: colors.axisLine,
        fillerColor: "rgba(86, 153, 255, 0.18)",
        // Ends resize (ew-resize cursor); the window between them moves (grab).
        handleIcon: ZOOM_HANDLE_ICON,
        handleSize: ZOOM_HANDLE_HEIGHT,
        handleStyle: { color: colors.tooltipBackground, borderColor: colors.text, borderWidth: 1 },
        moveHandleStyle: { color: colors.axisLine },
        emphasis: {
          handleStyle: { color: ZOOM_ACCENT, borderColor: colors.strongText, borderWidth: 1.5 },
        },
        dataBackground: {
          lineStyle: { color: colors.text, opacity: 0.5 },
          areaStyle: { color: colors.text, opacity: 0.12 },
        },
        selectedDataBackground: {
          lineStyle: { color: ZOOM_ACCENT },
          areaStyle: { color: ZOOM_ACCENT, opacity: 0.2 },
        },
        textStyle: { color: colors.text, fontSize: 10 },
        brushSelect: false,
      },
    ],
  };
}
