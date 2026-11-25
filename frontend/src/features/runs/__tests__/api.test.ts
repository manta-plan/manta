// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getJson, postJson } from "../../../api/manta";
import { createRun, getProjectRun, getRunSummary, listRuns, toFriendlyRunError } from "../api";

vi.mock("../../../api/manta", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/manta")>()),
  getJson: vi.fn(),
  postJson: vi.fn(),
}));

const mockedGetJson = vi.mocked(getJson);
const mockedPostJson = vi.mocked(postJson);

beforeEach(() => {
  vi.resetAllMocks();
});

const revision = "e5f2eacd-ba5c-463c-a663-3017ef904d1d";
const storeUrl = "s3://manta/4390c56f-0000-0000-0000-000000000000/ac-dc-meshed";

describe("toFriendlyRunError", () => {
  it("explains a missing revision", () => {
    const error = new ApiError(404, `Revision ${revision} not found in '${storeUrl}'`);
    const result = toFriendlyRunError(error);

    expect(result).toBeInstanceOf(ApiError);
    expect((result as ApiError).status).toBe(404);
    expect((result as ApiError).message).toBe(
      `The data record "ac-dc-meshed" is not available in this project (revision ${revision}). Please select another data record.`,
    );
  });

  it("leaves other 404 messages unchanged", () => {
    const error = new ApiError(404, "Project abc not found");

    expect(toFriendlyRunError(error)).toBe(error);
  });

  it("leaves a matching message with another status unchanged", () => {
    const error = new ApiError(500, `Revision ${revision} not found in '${storeUrl}'`);

    expect(toFriendlyRunError(error)).toBe(error);
  });

  it("leaves non-API errors unchanged", () => {
    const error = new Error("Failed to fetch");

    expect(toFriendlyRunError(error)).toBe(error);
  });
});

describe("project scoped requests", () => {
  it("lists the runs of the given project", async () => {
    mockedGetJson.mockResolvedValue({});
    await listRuns("uuid-a", { limit: 10, offset: 20, statuses: ["RUNNING", "COMPLETED"] });

    expect(mockedGetJson).toHaveBeenCalledWith(
      "/v1/runs?project_uuid=uuid-a&limit=10&offset=20&statuses=RUNNING&statuses=COMPLETED",
    );
  });

  it("summarises the runs of the given project", async () => {
    mockedGetJson.mockResolvedValue({});
    await getRunSummary("uuid-a");

    expect(mockedGetJson).toHaveBeenCalledWith("/v1/runs/summary?project_uuid=uuid-a");
  });

  it("creates a run with the project uuid and a store url from the same uuid", async () => {
    mockedPostJson.mockResolvedValue({});
    await createRun("uuid-a", {
      playbook: "pb",
      config: {} as never,
      dataRecord: { name: "ac-dc-meshed", revision_uuid: revision } as never,
    });

    const [url, body] = mockedPostJson.mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe("/v1/runs");
    expect(body.project_uuid).toBe("uuid-a");
    expect(body.data_record).toEqual({
      store_url: "s3://manta/uuid-a/ac-dc-meshed",
      revision_uuid: revision,
    });
    expect(mockedPostJson).not.toHaveBeenCalledWith("/v1/projects", expect.anything());
  });

  it("explains a missing revision when creating a run", async () => {
    mockedPostJson.mockRejectedValue(
      new ApiError(404, `Revision ${revision} not found in '${storeUrl}'`),
    );

    await expect(
      createRun("uuid-a", {
        playbook: "pb",
        config: {} as never,
        dataRecord: { name: "x", revision_uuid: revision } as never,
      }),
    ).rejects.toThrow(/is not available in this project/);
  });
});

describe("getProjectRun", () => {
  it("returns the run of the project", async () => {
    const run = { uuid: "r1", project_uuid: "uuid-a" };
    mockedGetJson.mockResolvedValue(run);

    await expect(getProjectRun("uuid-a", "r1")).resolves.toBe(run);
  });

  it("returns null for a run of another project", async () => {
    mockedGetJson.mockResolvedValue({ uuid: "r1", project_uuid: "uuid-b" });

    await expect(getProjectRun("uuid-a", "r1")).resolves.toBeNull();
  });

  it("returns null on 404", async () => {
    mockedGetJson.mockRejectedValue(new ApiError(404, "Run r1 not found"));

    await expect(getProjectRun("uuid-a", "r1")).resolves.toBeNull();
  });

  it("rethrows other errors", async () => {
    mockedGetJson.mockRejectedValue(new ApiError(500, "boom"));

    await expect(getProjectRun("uuid-a", "r1")).rejects.toThrow("boom");
  });
});
