// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it } from "vitest";
import { useLevelStore } from "../level-store";
import { seasonWindow } from "../seasons";

const WINTER = [11, 0, 1];

describe("seasonWindow", () => {
  it("keeps the season's months when the period spans the whole year", () => {
    const window = seasonWindow(
      {
        period: "2030",
        snapshots: 8760,
        start: "2030-01-01T00:00:00Z",
        end: "2030-12-31T23:00:00Z",
      },
      WINTER,
      "Winter",
    );
    expect(window?.months).toEqual(WINTER);
    expect(window?.start).toBe("2030-01-01T00:00:00Z");
  });

  it("is null when the span has none of the season", () => {
    expect(
      seasonWindow(
        {
          period: "2030",
          snapshots: 8760,
          start: "2030-06-01T00:00:00Z",
          end: "2030-06-30T23:00:00Z",
        },
        WINTER,
        "Winter",
      ),
    ).toBeNull();
  });
});

describe("level store", () => {
  beforeEach(() => useLevelStore.getState().resetForProject());

  it("drops the time window when the period changes", () => {
    const store = useLevelStore.getState();
    store.setPeriod("2030");
    store.setTimeWindow({ start: "2030-01-01T00:00:00Z", end: "2030-01-08T00:00:00Z", label: "w" });
    store.setPeriod("2040");
    expect(useLevelStore.getState().timeWindow).toBeNull();
  });

  it("forgets the period, window and locations when another project opens", () => {
    const store = useLevelStore.getState();
    store.setPeriod("2030");
    store.setSelectedLocations(["BE0 0"]);
    store.resetForProject();
    const after = useLevelStore.getState();
    expect([after.period, after.timeWindow, after.selectedLocations]).toEqual([null, null, []]);
  });
});
