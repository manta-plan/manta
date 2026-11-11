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

async function requestJson<ResponseBody>(url: string, init: RequestInit = {}) {
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

  return (await response.json()) as ResponseBody;
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
