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
 * Posts `body` and returns the response with its body unread, for a reply that is streamed
 * (`text/event-stream`). Sign-in, the 401 refresh-and-retry and the error mapping all happen
 * before the first byte is read, so a failure is an `ApiError` like any other request.
 */
export function postStream(url: string, body: unknown, signal?: AbortSignal) {
  return authorisedFetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });
}

async function requestJson<ResponseBody>(url: string, init: RequestInit = {}) {
  const response = await authorisedFetch(url, init);

  // A 204 (e.g. a delete) has no body to parse.
  if (response.status === 204) {
    return undefined as ResponseBody;
  }

  return (await response.json()) as ResponseBody;
}

// Sends a request as the signed-in user and returns the successful response, body unread.
// Throws an `ApiError` for any other status.
async function authorisedFetch(url: string, init: RequestInit = {}) {
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
    const { message, code } = await getResponseError(response);
    const error = new ApiError(response.status, message, getRetryAfterSeconds(response), code);

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

// What an error response says: `detail` is either the message, or a code with a message.
async function getResponseError(
  response: Response,
): Promise<{ message: string; code: string | null }> {
  const fallback = response.statusText || `Request failed with status ${response.status}`;

  try {
    const { detail } = (await response.json()) as { detail?: unknown };

    if (typeof detail === "string") {
      return { message: detail, code: null };
    }

    if (typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const { code, message } = detail as { code?: unknown; message?: unknown };

      return {
        message: typeof message === "string" ? message : fallback,
        code: typeof code === "string" ? code : null,
      };
    }
  } catch {
    // Fall back to the status text when the response is not JSON.
  }

  return { message: fallback, code: null };
}

// The wait a `Retry-After` header asks for, in whole seconds; null when it is absent or unreadable.
// The header is either a number of seconds or an HTTP date.
function getRetryAfterSeconds(response: Response) {
  const header = response.headers.get("Retry-After")?.trim();

  if (header === undefined || header === "") {
    return null;
  }

  if (/^\d+$/.test(header)) {
    return Number(header);
  }

  const retryAt = Date.parse(header);

  return Number.isNaN(retryAt) ? null : Math.max(0, Math.ceil((retryAt - Date.now()) / 1000));
}

export class ApiError extends Error {
  readonly status: number;
  /** Seconds the server asks to wait before trying again (`Retry-After`), when it says so. */
  readonly retryAfterSeconds: number | null;
  /** The server's own name for the failure (`detail.code`), when it gives one. */
  readonly code: string | null;

  constructor(
    status: number,
    message: string,
    retryAfterSeconds: number | null = null,
    code: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
    this.code = code;
  }
}
