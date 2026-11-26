import { describe, expect, it } from "vitest";
import { formatRunStatus, getRunStatusHint, hasUnfinishedRun, statusOptions } from "../status";

describe("formatRunStatus", () => {
  it("shows a run that waits for a slot as queued, not scheduled", () => {
    expect(formatRunStatus("SCHEDULED")).toBe("Queued");
    expect(formatRunStatus("scheduled")).toBe("Queued");
  });

  it("shows the other Prefect states by their name", () => {
    expect(formatRunStatus("RUNNING")).toBe("Running");
    expect(formatRunStatus("PENDING")).toBe("Pending");
    expect(formatRunStatus("NOT_STARTED")).toBe("Not Started");
  });

  it("labels the filter the same way, and still asks the backend for the Prefect state", () => {
    expect(statusOptions).toContainEqual({ label: "Queued", value: "SCHEDULED" });
  });
});

describe("getRunStatusHint", () => {
  it("says a queued run waits for a free slot", () => {
    expect(getRunStatusHint("SCHEDULED")).toMatch(/free slot/);
  });

  it("has nothing to add to the other statuses", () => {
    for (const status of ["PENDING", "RUNNING", "COMPLETED", "FAILED", "CRASHED", "CANCELLED"]) {
      expect(getRunStatusHint(status)).toBeNull();
    }
  });
});

describe("hasUnfinishedRun", () => {
  it("is true while a run is queued, pending or running", () => {
    for (const status of ["SCHEDULED", "PENDING", "RUNNING"]) {
      expect(hasUnfinishedRun([{ status: "COMPLETED" }, { status }])).toBe(true);
    }
  });

  it("is false once every run is finished, or there is none", () => {
    expect(
      hasUnfinishedRun([
        { status: "COMPLETED" },
        { status: "FAILED" },
        { status: "CRASHED" },
        { status: "CANCELLED" },
      ]),
    ).toBe(false);
    expect(hasUnfinishedRun([])).toBe(false);
  });
});
