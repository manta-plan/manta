import type { AttributeSpec } from "./record-server/types";

// Display text for record ids and values.

// Entity ids are PyPSA-Eur strings that start with their location:
// "way/87779917-380 0 onwind-2030". Under a location the rest says what it
// is ("0 onwind-2030"); ids that don't start with it (pipelines, loads named
// after their bus) stay whole.
export function entityLabel(entity: string, location: string | null): string {
  if (location && entity.startsWith(`${location} `)) return entity.slice(location.length + 1);
  return entity;
}

// Buses at a location are named "<location> <carrier>"; the AC bus is the
// location itself, so it reads as its carrier.
export function busLabel(bus: string, location: string, carrier: string): string {
  if (bus === location) return carrier;
  return bus.startsWith(`${location} `) ? bus.slice(location.length + 1) : bus;
}

const NUMBER = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 4 });

export function formatNumber(value: number): string {
  return NUMBER.format(value);
}

export function isWkt(text: string): boolean {
  return /^\s*(MULTI)?(POLYGON|LINESTRING|POINT)\s*\(/i.test(text);
}

// A stored value (as text) by the manifest's dtype, with its unit.
export function formatValue(
  text: string | null,
  spec?: Pick<AttributeSpec, "dtype" | "unit">,
): string {
  if (text === null || text === "") return "—";
  if (isWkt(text)) {
    const points = (text.match(/-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?/g) ?? []).length;
    return `${text.trim().split(/\s|\(/)[0].toLowerCase()}, ${points} points`;
  }
  const dtype = spec?.dtype;
  let shown = text;
  if (
    dtype === "float" ||
    dtype === "int" ||
    (dtype === undefined && /^-?\d+(\.\d+)?(e[-+]?\d+)?$/i.test(text))
  ) {
    const number = Number(text);
    if (Number.isFinite(number)) shown = formatNumber(number);
    else if (text === "inf" || text === "Infinity") shown = "∞";
  }
  return spec?.unit && shown !== "—" ? `${shown} ${spec.unit}` : shown;
}

// Arrow returns timestamps as epoch milliseconds.
// A scenario's after / before, as ×1.3.
export function formatRatio(ratio: number | null): string {
  return ratio === null || !Number.isFinite(ratio) ? "—" : `×${Number(ratio.toPrecision(3))}`;
}

export function formatTimestamp(value: unknown): string {
  if (typeof value === "number")
    return new Date(value).toISOString().slice(0, 16).replace("T", " ").replace(" 00:00", "");
  return String(value ?? "—");
}

export function formatCapacity(megawatts: number, unit = "MW"): string {
  if (Math.abs(megawatts) >= 1000)
    return `${formatNumber(Math.round(megawatts / 100) / 10)} G${unit.slice(1)}`;
  return `${formatNumber(Math.round(megawatts))} ${unit}`;
}
