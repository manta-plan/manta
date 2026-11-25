import { postJson } from "../../api/manta";
import { clearSession, getRefreshToken, startSession } from "./session";
import type { LoginResponse } from "./types";

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
  startSession(tokens, remember);
}

// Creates a fresh guest account on the backend and signs into it.
export async function loginAsGuest() {
  const tokens = await postJson<LoginResponse>("/v1/auth/guest", {});
  startSession(tokens, true);
}

export async function logout() {
  const refreshToken = getRefreshToken();

  // Sign out locally first, so the UI never waits on the network and the user
  // is signed out even if the request below fails.
  clearSession();

  if (refreshToken === null) {
    return;
  }

  try {
    await postJson<void>("/v1/auth/logout", { refresh_token: refreshToken });
  } catch {
    // The Keycloak session stays active until its refresh token expires, but
    // this browser no longer holds any token for it.
  }
}
