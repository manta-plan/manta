import { SNAPSHOT_COUNT } from "./inspect-filters";

// The dummy hour-by-hour dispatch behind the Power Dispatch widgets and the
// custom widget's dispatch table. Generated placeholders, not solver output.

const BATTERY_POWER = 60;
const BATTERY_ENERGY = 240;
const ELECTROLYSIS_POWER = 140;
export const STACK_ORDER = [
  "nuclear",
  "hydro",
  "Onshore Wind",
  "offwind-dc",
  "solar-pv-utility",
  "Battery Storage",
  "gas",
  "H2 Electrolysis",
];

export function round(value: number) {
  return Math.round(value * 10) / 10;
}

export interface Simulation {
  carriers: Record<string, number[]>;
  load: number[];
  storage: Record<string, number[]>;
  prices: number[];
}

// GW per hour from the hour of the year: demand and wind run higher in
// winter, solar follows daylight and season, and a simple battery and
// electrolyser soak up surpluses before gas covers deficits.
export function simulate(start: number, end: number): Simulation {
  const carriers: Record<string, number[]> = Object.fromEntries(
    STACK_ORDER.map((carrier) => [carrier, []]),
  );
  const load: number[] = [];
  const storage: Record<string, number[]> = {
    "Battery Storage": [],
    "hydro-phs": [],
    "H2 Store": [],
  };
  const prices: number[] = [];
  let battery = BATTERY_ENERGY / 2;

  for (let hour = start; hour <= end; hour++) {
    const hourOfDay = hour % 24;
    const day = Math.floor(hour / 24);
    // 1 Jan 2040 is a Sunday.
    const isWeekend = day % 7 === 0 || day % 7 === 6;
    const season = Math.cos((2 * Math.PI * hour) / SNAPSHOT_COUNT - 0.1); // 1 mid-winter, -1 mid-summer
    const demand =
      430 +
      60 * season +
      70 * Math.sin(((hourOfDay - 9) / 24) * 2 * Math.PI) -
      (isWeekend ? 45 : 0);
    const sunny = 0.75 + 0.25 * Math.sin(day * 1.7);
    const solar =
      Math.max(0, Math.sin(((hourOfDay - 6) / 12) * Math.PI)) * 380 * sunny * (1 - 0.45 * season);
    const wind = Math.max(
      20,
      (190 + 140 * Math.sin(hour / 26) + 30 * Math.sin(hour / 5)) * (1 + 0.35 * season),
    );
    const offshore = Math.max(10, (90 + 60 * Math.sin(hour / 31 + 1)) * (1 + 0.35 * season));
    const nuclear = 95;
    const hydro = 45 + 15 * Math.sin(((hourOfDay - 18) / 24) * 2 * Math.PI) - 8 * season;

    const residual = demand - (solar + wind + offshore + nuclear + hydro);
    let batteryFlow = 0;
    let electrolysis = 0;
    let gas = 0;
    if (residual < 0) {
      // Surplus charges the battery first, then runs electrolysis; the rest is curtailed.
      batteryFlow = -Math.min(-residual, BATTERY_POWER, (BATTERY_ENERGY - battery) / 0.9);
      electrolysis = -Math.min(-residual + batteryFlow, ELECTROLYSIS_POWER);
      battery -= batteryFlow * 0.9;
    } else {
      batteryFlow = Math.min(residual, BATTERY_POWER, battery * 0.9);
      gas = residual - batteryFlow;
      battery -= batteryFlow / 0.9;
    }

    carriers.nuclear.push(nuclear);
    carriers.hydro.push(round(hydro));
    carriers["Onshore Wind"].push(round(wind));
    carriers["offwind-dc"].push(round(offshore));
    carriers["solar-pv-utility"].push(round(solar));
    carriers["Battery Storage"].push(round(batteryFlow));
    carriers.gas.push(round(gas));
    carriers["H2 Electrolysis"].push(round(electrolysis));
    load.push(round(demand));
    storage["Battery Storage"].push(round((battery / BATTERY_ENERGY) * 100));
    // Pumped hydro cycles daily; the H2 store fills over summer and drains in winter.
    storage["hydro-phs"].push(round(55 + 30 * Math.sin(((hourOfDay - 8) / 24) * 2 * Math.PI)));
    storage["H2 Store"].push(round(50 - 32 * season + 3 * Math.sin(hour / 12)));
    // Gas sets the price when it runs; otherwise it sinks with the surplus.
    prices.push(
      round(residual > 0 ? 55 + Math.min(gas, 200) * 0.3 : Math.max(0, 25 + residual * 0.12)),
    );
  }

  return { carriers, load, storage, prices };
}
