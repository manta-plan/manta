import { clearSession, getValidAccessToken, refreshAccessToken } from "../features/auth/session";

export function getJson<ResponseBody>(url: string) {
  return requestJson<ResponseBody>(url);
}

export function postJson<ResponseBody>(url: string, body: unknown) {
  return requestJson<ResponseBody>(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

export function patchJson<ResponseBody>(url: string, body: unknown) {
  return requestJson<ResponseBody>(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

export function deleteRequest(url: string) {
  return requestJson<void>(url, { method: "DELETE" });
}

/**
 * POSTs like postJson, but resolves to the response itself as soon as its
 * headers arrive, for a caller that reads the body as a stream. Aborting
 * `signal` cancels the request, also while the body is being read.
 */
export function postStream(url: string, body: unknown, signal?: AbortSignal) {
  return request(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });
}

async function requestJson<ResponseBody>(url: string, init: RequestInit = {}) {
  const response = await request(url, init);

  // A 204 (e.g. a delete) has no body to parse.
  if (response.status === 204) {
    return undefined as ResponseBody;
  }

  return (await response.json()) as ResponseBody;
}

// Sends an authenticated request and resolves to its successful response.
// Throws an ApiError for any other status.
async function request(url: string, init: RequestInit = {}) {
  const accessToken = await getValidAccessToken();
  let response = await sendRequest(url, init, accessToken);

  // The backend rejected a token we thought was valid (e.g. revoked, or the
  // local clock is off). Refresh once and retry before giving up.
  if (response.status === 401 && accessToken !== null) {
    const refreshedAccessToken = await refreshAccessToken(accessToken);

    if (refreshedAccessToken !== null) {
      response = await sendRequest(url, init, refreshedAccessToken);
    }
  }

  if (!response.ok) {
    const error = new ApiError(response.status, await getResponseErrorMessage(response));

    // An authenticated request was still rejected after a refresh, so the
    // user is no longer known to the backend. Clearing the session sends them
    // back to the sign-in page.
    if (response.status === 401 && accessToken !== null) {
      clearSession();
    }

    throw error;
  }

  return response;
}

function sendRequest(url: string, init: RequestInit, accessToken: string | null) {
  const headers = new Headers(init.headers);

  if (accessToken !== null) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  return fetch(url, { ...init, headers });
}

async function getResponseErrorMessage(response: Response) {
  try {
    const errorBody = (await response.json()) as { detail?: unknown };

    if (typeof errorBody.detail === "string") {
      return errorBody.detail;
    }
  } catch {
    // Fall back to the status text below when the response is not JSON.
  }

  return response.statusText || `Request failed with status ${response.status}`;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
