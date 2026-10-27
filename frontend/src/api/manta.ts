import { clearSession, getAccessToken } from "../features/auth/session";

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
  const accessToken = getAccessToken();
  const headers = new Headers(init.headers);

  if (accessToken !== null) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(url, { ...init, headers });

  if (!response.ok) {
    const error = new ApiError(response.status, await getResponseErrorMessage(response));

    // An authenticated request was rejected, so the token has expired or the
    // user is no longer known to the backend. Clearing the session sends them
    // back to the sign-in page.
    if (response.status === 401 && accessToken !== null) {
      clearSession();
    }

    throw error;
  }

  return (await response.json()) as ResponseBody;
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
