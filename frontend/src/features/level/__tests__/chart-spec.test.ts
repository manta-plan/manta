// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from "vitest";
import {
  distributionOf,
  durationCurve,
  formatNumber,
  isPerUnit,
  isRate,
  sumUnit,
  timeIso,
  timeLabel,
} from "../chart/spec";

describe("chart spec helpers", () => {
  it("reads MW and MWh sums in GW and GWh, other units as they are", () => {
    expect(sumUnit("MW")).toEqual({ unit: "GW", scale: 1e-3 });
    expect(sumUnit("MWh")).toEqual({ unit: "GWh", scale: 1e-3 });
    expect(sumUnit("per unit")).toEqual({ unit: "per unit", scale: 1 });
    expect(sumUnit(null)).toEqual({ unit: "", scale: 1 });
  });

  it("never sums per unit values or prices", () => {
    expect(isPerUnit("per unit")).toBe(true);
    expect(isPerUnit("MW")).toBe(false);
    expect(isRate("currency/MWh")).toBe(true);
    expect(isRate("EUR/MWh")).toBe(true);
    expect(isRate("MW")).toBe(false);
  });

  it("builds quantiles per position, skipping nulls", () => {
    const d = distributionOf([
      [1, 10, null],
      [2, 20, 5],
      [3, 30, 7],
      [4, 40, null],
      [5, 50, 9],
    ]);
    expect(d.count).toBe(5);
    expect(d.min).toEqual([1, 10, 5]);
    expect(d.median).toEqual([3, 30, 7]);
    expect(d.max).toEqual([5, 50, 9]);
    expect(d.p25[0]).toBe(2);
    expect(d.p75[0]).toBe(4);
  });

  it("sorts a duration curve high to low against cumulative hours", () => {
    const curve = durationCurve([1, null, 3, 2], [1, 1, 2, 1]);
    expect(curve.values).toEqual([3, 2, 1]);
    expect(curve.x).toEqual([2, 3, 4]);
  });

  it("labels times in UTC", () => {
    const ms = Date.UTC(2013, 0, 1, 9, 5);
    expect(timeLabel(ms)).toBe("1 Jan 09:05");
    expect(timeIso(ms)).toBe("2013-01-01 09:05");
  });

  it("formats numbers with fewer decimals as they grow, and a dash for none", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatNumber(1234.56)).toBe((1235).toLocaleString());
    expect(formatNumber(0.12345)).toBe(
      (0.123).toLocaleString(undefined, { maximumFractionDigits: 3 }),
    );
  });
});
