import { postJson } from "../../api/manta";
import { decodeTokenClaims, startSession } from "./session";
import type { LoginResponse, RegisterResponse } from "./types";

type LoginParams = {
  username: string;
  password: string;
  remember: boolean;
};

export async function login({ username, password, remember }: LoginParams) {
  const tokens = await postJson<LoginResponse>("/v1/auth/login", {
    username,
    password,
  });
  const claims = decodeTokenClaims(tokens.access_token);

  if (claims === null) {
    throw new Error("Received an invalid access token.");
  }

  // The backend only authorizes users it has a record of, and login does not
  // create one. Register is idempotent, so calling it on every login is safe.
  await postJson<RegisterResponse>("/v1/auth/register", {
    username: claims.preferred_username ?? username,
    idp_subject: claims.sub,
    idp_source: claims.iss,
  });

  startSession(tokens, remember);
}
