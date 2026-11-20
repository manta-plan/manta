import { useMemo } from "react";
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
