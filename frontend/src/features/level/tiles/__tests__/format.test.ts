// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from "vitest";
import { capacityUnit, formatMega, formatNumber, formatPercent, plural } from "../format";

describe("tile formatting", () => {
  it("shows a dash for a missing number", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatMega(null, "W")).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
  });

  it("keeps about three significant figures", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber(1234.5)).toBe("1,235");
    expect(formatNumber(42.26)).toBe("42.3");
    expect(formatNumber(3.14159)).toBe("3.14");
    expect(formatNumber(3.14159, 0)).toBe("3");
  });

  it("picks the prefix that keeps a mega-unit readable", () => {
    expect(formatMega(500, "W")).toBe("500 MW");
    expect(formatMega(1500, "W")).toBe("1.50 GW");
    expect(formatMega(2_500_000, "Wh")).toBe("2.50 TWh");
    expect(formatMega(0.5, "W")).toBe("500 kW");
    expect(formatMega(0, "VA")).toBe("0 MVA");
    expect(formatMega(1200, "W·km")).toBe("1.20 GW·km");
  });

  it("stops at the largest and smallest prefix", () => {
    expect(formatMega(1e12, "W")).toBe("1,000 PW");
    expect(formatMega(0.0000001, "W")).toBe("0.00 kW");
  });

  it("formats a share as a percentage", () => {
    expect(formatPercent(0.4567)).toBe("45.7%");
    expect(formatPercent(1)).toBe("100.0%");
  });

  it("pluralises", () => {
    expect(plural(1, "carrier")).toBe("1 carrier");
    expect(plural(2, "carrier")).toBe("2 carriers");
    expect(plural(0, "line")).toBe("0 lines");
    expect(plural(2, "substation", "substations")).toBe("2 substations");
  });

  it("names the unit of a capacity attribute", () => {
    expect(capacityUnit("e_nom")).toBe("Wh");
    expect(capacityUnit("s_nom")).toBe("VA");
    expect(capacityUnit("p_nom")).toBe("W");
    expect(capacityUnit(null)).toBe("W");
  });
});
