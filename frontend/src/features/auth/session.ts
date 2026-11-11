import { useSyncExternalStore } from "react";

import type { RefreshResponse, TokenResponse } from "./types";

// Access token, refresh token and their expiries live under one key so another
// tab never sees a new access token paired with an old refresh token.
const sessionStorageKey = "manta.session";
// Project UUIDs are owned per user, so the cached default project must not
// outlive the session that created it.
const sessionScopedStorageKeys = ["manta.defaultProjectUuid"];
// Refresh this long before the access token expires, so a request doesn't
// leave with a token that expires in flight.
const accessTokenRefreshLeewayMs = 30_000;
const refreshLockName = "manta.refresh";

export type TokenClaims = {
  sub: string;
  iss: string;
  exp?: number;
  preferred_username?: string;
};

export type SessionUser = {
  username: string;
  claims: TokenClaims;
};

type StoredSession = {
  accessToken: string;
  refreshToken: string;
  accessExpiresAt: number;
  // null when the refresh token doesn't expire (Keycloak sends
  // refresh_expires_in: 0 for offline tokens).
  refreshExpiresAt: number | null;
};

export function decodeTokenClaims(accessToken: string): TokenClaims | null {
  const payload = accessToken.split(".")[1];

  if (payload === undefined) {
    return null;
  }

  try {
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
    const claims = JSON.parse(new TextDecoder().decode(bytes)) as Partial<TokenClaims>;

    if (typeof claims.sub !== "string" || typeof claims.iss !== "string") {
      return null;
    }

    return claims as TokenClaims;
  } catch {
    return null;
  }
}

// Returns an access token that isn't about to expire, refreshing it first if
// needed. Returns null when there is no session or it can no longer be
// refreshed. Throws if the refresh fails for any other reason (network, 5xx),
// leaving the session in place.
export async function getValidAccessToken(): Promise<string | null> {
  const stored = readStoredSession();

  if (stored === null) {
    return null;
  }

  const { accessToken, accessExpiresAt } = stored.session;

  return expiresWithin(accessExpiresAt, accessTokenRefreshLeewayMs)
    ? refreshAccessToken(accessToken)
    : accessToken;
}

let inFlightRefresh: Promise<string | null> | null = null;

// Swaps the refresh token for a new token set and returns the new access
// token. staleAccessToken is the token the caller found expired or had
// rejected: if storage already holds a different one, another request or tab
// has refreshed in the meantime and that token is returned instead.
export function refreshAccessToken(staleAccessToken: string): Promise<string | null> {
  // Concurrent requests in this tab share one refresh call.
  inFlightRefresh ??= withRefreshLock(() => runRefresh(staleAccessToken)).finally(() => {
    inFlightRefresh = null;
  });

  return inFlightRefresh;
}

export function useSessionUser(): SessionUser | null {
  const accessToken = useSyncExternalStore(subscribe, getSignedInAccessToken);
  const claims = accessToken === null ? null : decodeTokenClaims(accessToken);

  if (claims === null) {
    return null;
  }

  return { username: claims.preferred_username ?? claims.sub, claims };
}

export function startSession(tokens: TokenResponse, remember: boolean) {
  clearSession();
  writeStoredSession(remember ? window.localStorage : window.sessionStorage, tokens);
}

export function clearSession() {
  for (const storage of [window.sessionStorage, window.localStorage]) {
    storage.removeItem(sessionStorageKey);
    sessionScopedStorageKeys.forEach((key) => storage.removeItem(key));
  }
  notifyListeners();
}

// The user counts as signed in while the refresh token is live, even if the
// access token has expired: the next request refreshes it. Returns the access
// token only so useSessionUser can read the username from its claims.
function getSignedInAccessToken() {
  const stored = readStoredSession();

  if (stored === null || isRefreshTokenExpired(stored.session)) {
    return null;
  }

  return stored.session.accessToken;
}

async function runRefresh(staleAccessToken: string): Promise<string | null> {
  const stored = readStoredSession();

  if (stored === null) {
    return null;
  }

  if (stored.session.accessToken !== staleAccessToken) {
    return stored.session.accessToken;
  }

  if (isRefreshTokenExpired(stored.session)) {
    clearSession();
    return null;
  }

  const response = await fetch("/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: stored.session.refreshToken }),
  });

  if (response.status === 401) {
    // The refresh token is invalid, expired or revoked. Only end the session
    // if it's still the one we tried: the user may have signed in again in
    // another tab while this request was in flight.
    if (readStoredSession()?.session.refreshToken === stored.session.refreshToken) {
      clearSession();
    }
    return null;
  }

  if (!response.ok) {
    throw new Error(`Token refresh failed with status ${response.status}`);
  }

  const tokens = (await response.json()) as RefreshResponse;
  // Keycloak issues a new refresh token on every refresh; the old one may stop
  // working once used, so the whole set is replaced. Writing to the storage
  // the session already lives in keeps the "remember me" choice.
  writeStoredSession(stored.storage, tokens);

  return tokens.access_token;
}

// Serializes refreshes across tabs, so two tabs don't spend the same refresh
// token at once. The Web Locks API only exists in secure contexts (HTTPS or
// localhost); without it, tabs can race, which Keycloak tolerates as long as
// "Revoke Refresh Token" is off.
function withRefreshLock<T>(callback: () => Promise<T>): Promise<T> {
  if (navigator.locks === undefined) {
    return callback();
  }

  return navigator.locks.request(refreshLockName, callback);
}

function readStoredSession(): { session: StoredSession; storage: Storage } | null {
  for (const storage of [window.sessionStorage, window.localStorage]) {
    const raw = storage.getItem(sessionStorageKey);

    if (raw === null) {
      continue;
    }

    try {
      const session = JSON.parse(raw) as Partial<StoredSession>;

      if (
        typeof session.accessToken === "string" &&
        typeof session.refreshToken === "string" &&
        typeof session.accessExpiresAt === "number" &&
        (typeof session.refreshExpiresAt === "number" || session.refreshExpiresAt === null)
      ) {
        return { session: session as StoredSession, storage };
      }
    } catch {
      // Treat unparseable entries as no session.
    }
  }

  return null;
}

function writeStoredSession(storage: Storage, tokens: TokenResponse) {
  // Expiries come from the relative lifetimes Keycloak returns, measured from
  // when the response arrived.
  const now = Date.now();
  const session: StoredSession = {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    accessExpiresAt: now + tokens.expires_in * 1000,
    refreshExpiresAt:
      tokens.refresh_expires_in === 0 ? null : now + tokens.refresh_expires_in * 1000,
  };

  storage.setItem(sessionStorageKey, JSON.stringify(session));
  notifyListeners();
}

function isRefreshTokenExpired(session: StoredSession) {
  return session.refreshExpiresAt !== null && expiresWithin(session.refreshExpiresAt, 0);
}

function expiresWithin(expiresAt: number, marginMs: number) {
  return expiresAt - marginMs <= Date.now();
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  // Keep tabs in sync when another tab signs in, refreshes or signs out via
  // localStorage.
  window.addEventListener("storage", listener);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function notifyListeners() {
  listeners.forEach((listener) => listener());
}
