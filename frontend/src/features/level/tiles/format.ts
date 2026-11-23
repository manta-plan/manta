// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

// Number and unit formatting for the tiles: a value in a base unit (MW, MWh,
// MVA, MW·km) shown with the prefix that keeps it readable (MW → GW → TW).

const PREFIXES = ["k", "M", "G", "T", "P"] as const;

/** A number with about three significant figures, grouped en-GB style. */
export function formatNumber(value: number | null | undefined, digits?: number): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const size = Math.abs(value);
  const decimals = digits ?? (size === 0 || size >= 100 ? 0 : size >= 10 ? 1 : 2);
  return value.toLocaleString("en-GB", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  });
}

/**
 * A quantity given in mega-units ("MW", "MWh", "MVA", "MW·km"): `unit` is the
 * part after the prefix ("W", "Wh", "VA", "W·km"). Picks k…P so the number
 * stays between 1 and 1,000 where it can.
 */
export function formatMega(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  let index = 1; // M
  let scaled = value;
  while (Math.abs(scaled) >= 1000 && index < PREFIXES.length - 1) {
    scaled /= 1000;
    index += 1;
  }
  while (Math.abs(scaled) > 0 && Math.abs(scaled) < 1 && index > 0) {
    scaled *= 1000;
    index -= 1;
  }
  return `${formatNumber(scaled)} ${PREFIXES[index]}${unit}`;
}

/** A share (0–1) as a percentage. */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${formatNumber(value * 100, 1)}%`;
}

export function plural(count: number, noun: string, many = `${noun}s`): string {
  return `${formatNumber(count, 0)} ${count === 1 ? noun : many}`;
}

/** The unit (after the mega prefix) of a capacity attribute. */
export function capacityUnit(attribute: string | null): string {
  if (attribute === "e_nom") return "Wh";
  if (attribute === "s_nom") return "VA";
  return "W";
}
