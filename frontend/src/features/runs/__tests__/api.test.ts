import { describe, expect, it } from "vitest";
import { ApiError } from "../../../api/manta";
import { toFriendlyRunError } from "../api";

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
