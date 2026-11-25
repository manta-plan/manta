// Dummy result values shared by the built-in widgets and the custom
// widget's result tables, so a custom copy of a built-in shows the same
// numbers. Fixed placeholders, not solver output.

export const GENERATOR_SUPPLY: [string, number][] = [
  ["biogas", 860],
  ["gas", 1510],
  ["import H2", 590],
  ["offwind-ac-fb-r", 310],
  ["offwind-dc-fb-oh", 320],
  ["offwind-dc-fl-oh", 390],
  ["oil primary", 2690],
  ["Onshore Wind", 1240],
  ["solar-pv-rooftop", 450],
  ["solar-pv-utility", 860],
  ["solid biomass", 1370],
  ["uranium", 1660],
];

export const WITHDRAWAL: [string, number][] = [
  ["biomass final energy demand", 740],
  ["electricity", 4630],
  ["exogenous gas demand", 1700],
  ["H2 exogenous demand", 1040],
  ["kerosene for aviation", 610],
  ["land transport oil", 1940],
  ["shipping oil", 260],
];

function hashString(text: string) {
  let hash = 0;
  for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) % 100003;
  return hash;
}

// Dummy €/MWh per area — H2 trades well above AC, as in the reference plot.
export function busPrice(area: string, carrier: string) {
  const spread = (hashString(`${carrier}:${area}`) % 1000) / 1000;
  return carrier === "H2" ? 70 + spread * 50 : 5 + spread * 75;
}

// bn €/a, annualised.
export const COST_BY_COMPONENT: [string, number, number][] = [
  ["Generator", 92.4, 38.1],
  ["Link", 121.7, 64.3],
  ["Line", 18.2, 0],
  ["StorageUnit", 6.1, 0.5],
  ["Store", 9.3, 0.3],
];

// bn €/a, annualised — the largest carriers by total cost.
export const COST_BY_CARRIER: [string, number, number][] = [
  ["gas", 14.2, 41.8],
  ["Onshore Wind", 38.6, 4.1],
  ["solar-pv-utility", 31.9, 1.2],
  ["electricity distribution grid", 29.4, 0],
  ["nuclear", 17.5, 9.8],
  ["offwind-dc", 21.3, 1.9],
  ["H2 Electrolysis", 18.7, 0.8],
  ["solar-pv-rooftop", 16.2, 0.6],
  ["AC", 12.4, 0],
  ["biomass", 4.9, 7.2],
];

// TWh curtailed over the year and the share of available energy it represents.
export const CURTAILMENT: [string, number, number][] = [
  ["solar-pv-utility", 42.3, 6.1],
  ["Onshore Wind", 31.2, 4.2],
  ["offwind-dc", 12.4, 3.5],
  ["offwind-ac", 8.9, 2.8],
  ["solar-pv-rooftop", 6.1, 1.9],
  ["run of river", 2.2, 1.4],
];

// Mt CO2/a in 2040 — removals are negative.
export const EMISSIONS_BY_SECTOR: [string, number][] = [
  ["Industry", 210],
  ["Power", 120],
  ["Aviation", 110],
  ["Land transport", 95],
  ["Heating", 85],
  ["Shipping", 70],
  ["BECCS", -130],
  ["DAC", -150],
];
