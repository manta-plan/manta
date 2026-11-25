// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";
import { ROW_HEIGHT, rowRange } from "../use-row-window";

describe("row window", () => {
  it("renders the first rows plus an overscan at the top", () => {
    const { start, end } = rowRange(0, 270, 5000);
    expect(start).toBe(0);
    expect(end).toBe(Math.ceil(270 / ROW_HEIGHT) + 12);
  });

  it("starts above the viewport by the overscan when scrolled", () => {
    const { start, end } = rowRange(ROW_HEIGHT * 100, ROW_HEIGHT * 20, 5000);
    expect(start).toBe(88);
    expect(end).toBe(132);
  });

  it("never runs past the last row, or before the first", () => {
    expect(rowRange(ROW_HEIGHT * 4990, 600, 5000).end).toBe(5000);
    expect(rowRange(0, 600, 3)).toEqual({ start: 0, end: 3 });
    expect(rowRange(0, 600, 0)).toEqual({ start: 0, end: 0 });
  });
});
