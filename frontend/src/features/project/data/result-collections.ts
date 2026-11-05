// Dummy per-run result tables for the Result Inspector — stands in for the
// real solver output tables a succeeded run would produce. Each collection
// is one selectable "table" in the collection switcher.

export interface ResultCollection {
  id: string;
  label: string;
  columns: string[];
  rows: (string | number)[][];
}

export const RESULT_COLLECTIONS: ResultCollection[] = [
  {
    id: "capacity-mix",
    label: "Capacity Mix",
    columns: ["Technology", "Installed (MW)", "Retired (MW)", "Net Change (MW)"],
    rows: [
      ["Offshore Wind", 12480, 0, 2140],
      ["Onshore Wind", 8320, 210, -60],
      ["Solar PV", 6740, 0, 1890],
      ["Gas CCGT", 15200, 1400, -1400],
      ["Nuclear", 5920, 0, 0],
      ["Battery Storage", 3180, 0, 1120],
      ["Coal", 0, 2600, -2600],
    ],
  },
  {
    id: "generation-by-tech",
    label: "Generation by Technology",
    columns: ["Technology", "Annual (GWh)", "Capacity Factor (%)", "Curtailed (GWh)"],
    rows: [
      ["Offshore Wind", 43800, 40.1, 1120],
      ["Onshore Wind", 21900, 30.0, 640],
      ["Solar PV", 7360, 12.5, 90],
      ["Gas CCGT", 31500, 23.7, 0],
      ["Nuclear", 46700, 90.1, 0],
      ["Battery Storage", 2140, 7.7, 0],
    ],
  },
  {
    id: "emissions",
    label: "Emissions",
    columns: ["Year", "CO₂ (Mt)", "vs. Base Case (%)"],
    rows: [
      [2026, 18.4, -4.2],
      [2028, 14.1, -18.6],
      [2030, 9.7, -38.9],
      [2032, 6.2, -55.1],
      [2035, 3.1, -71.4],
    ],
  },
  {
    id: "storage-dispatch",
    label: "Storage Dispatch",
    columns: ["Asset", "Cycles/Year", "Charge (GWh)", "Discharge (GWh)", "Round-Trip Eff. (%)"],
    rows: [
      ["Battery Fleet — North", 312, 890, 810, 91.0],
      ["Battery Fleet — South", 287, 760, 695, 91.4],
      ["Pumped Hydro — Site A", 198, 1240, 1080, 87.1],
    ],
  },
];
