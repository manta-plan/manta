import { describe, expect, it } from "vitest";
import { draftStatus, splitStatusFilter, summarizeRunStatuses } from "../status-groups";

describe("summarizeRunStatuses", () => {
  it("groups the Prefect states", () => {
    const counts = summarizeRunStatuses({
      total: 20,
      statuses: {
        COMPLETED: 5,
        SCHEDULED: 1,
        PENDING: 2,
        RUNNING: 3,
        FAILED: 4,
        CRASHED: 1,
        CANCELLED: 2,
        CANCELLING: 1,
        PAUSED: 1,
      },
    });

    expect(counts).toEqual({
      total: 20,
      succeeded: 5,
      inProgress: 6,
      failed: 5,
      successRate: 50,
    });
  });

  it("counts cancelled, cancelling and paused runs only in the total", () => {
    const counts = summarizeRunStatuses({
      total: 4,
      statuses: { CANCELLED: 2, CANCELLING: 1, PAUSED: 1 },
    });

    expect(counts).toMatchObject({ total: 4, succeeded: 0, inProgress: 0, failed: 0 });
  });

  it("has no success rate until a run has finished", () => {
    expect(summarizeRunStatuses({ total: 0, statuses: {} }).successRate).toBeNull();
    expect(summarizeRunStatuses({ total: 2, statuses: { RUNNING: 2 } }).successRate).toBeNull();
  });

  it("rounds the success rate over finished runs only", () => {
    const counts = summarizeRunStatuses({
      total: 9,
      statuses: { COMPLETED: 2, FAILED: 1, RUNNING: 6 },
    });

    expect(counts.successRate).toBe(67);
  });

  it("reads a state in any case", () => {
    const counts = summarizeRunStatuses({ total: 2, statuses: { completed: 1, Failed: 1 } });

    expect(counts).toMatchObject({ succeeded: 1, failed: 1 });
  });
});

describe("splitStatusFilter", () => {
  it("lists drafts and asks the backend for everything when nothing is selected", () => {
    expect(splitStatusFilter([])).toEqual({
      serverStatuses: [],
      showsDrafts: true,
      isDraftOnly: false,
    });
  });

  it("keeps drafts out when only backend states are selected", () => {
    expect(splitStatusFilter(["FAILED"])).toEqual({
      serverStatuses: ["FAILED"],
      showsDrafts: false,
      isDraftOnly: false,
    });
  });

  it("never sends Draft to the backend", () => {
    expect(splitStatusFilter([draftStatus, "RUNNING"])).toEqual({
      serverStatuses: ["RUNNING"],
      showsDrafts: true,
      isDraftOnly: false,
    });
  });

  it("does not ask the backend when only Draft is selected", () => {
    expect(splitStatusFilter([draftStatus])).toEqual({
      serverStatuses: [],
      showsDrafts: true,
      isDraftOnly: true,
    });
  });
});
