// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { nextDimension } from "./feedback-image";

describe("nextDimension", () => {
  it("starts at the largest step", () => {
    expect(nextDimension(null)).toBe(2560);
  });

  it("steps down 2560 -> 1920 -> 1280", () => {
    expect(nextDimension(2560)).toBe(1920);
    expect(nextDimension(1920)).toBe(1280);
  });

  it("returns null once the smallest step is used", () => {
    expect(nextDimension(1280)).toBeNull();
    expect(nextDimension(800)).toBeNull();
  });

  it("skips steps at or above the current size", () => {
    expect(nextDimension(2000)).toBe(1920);
    expect(nextDimension(5000)).toBe(2560);
  });
});
