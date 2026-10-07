import { useSyncExternalStore } from "react";

const accessTokenStorageKey = "manta.accessToken";
// Project UUIDs are owned per user, so the cached default project must not
// outlive the session that created it.
const sessionScopedStorageKeys = ["manta.defaultProjectUuid"];

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

export function getAccessToken() {
  const accessToken =
    window.sessionStorage.getItem(accessTokenStorageKey) ??
    window.localStorage.getItem(accessTokenStorageKey);

  if (accessToken === null) {
    return null;
  }

  const claims = decodeTokenClaims(accessToken);

  return claims === null || isExpired(claims) ? null : accessToken;
}

export function useSessionUser(): SessionUser | null {
  const accessToken = useSyncExternalStore(subscribe, getAccessToken);
  const claims = accessToken === null ? null : decodeTokenClaims(accessToken);

  if (claims === null) {
    return null;
  }

  return { username: claims.preferred_username ?? claims.sub, claims };
}

export function startSession(accessToken: string, remember: boolean) {
  clearSession();
  const storage = remember ? window.localStorage : window.sessionStorage;
  storage.setItem(accessTokenStorageKey, accessToken);
  notifyListeners();
}

export function clearSession() {
  for (const storage of [window.sessionStorage, window.localStorage]) {
    storage.removeItem(accessTokenStorageKey);
    sessionScopedStorageKeys.forEach((key) => storage.removeItem(key));
  }
  notifyListeners();
}

function isExpired(claims: TokenClaims) {
  return claims.exp !== undefined && claims.exp * 1000 <= Date.now();
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  // Keep tabs in sync when another tab signs in or out via localStorage.
  window.addEventListener("storage", listener);

  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function notifyListeners() {
  listeners.forEach((listener) => listener());
}
