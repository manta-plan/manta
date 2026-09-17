export async function getJson<ResponseBody>(url: string) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new ApiError(response.status, await getResponseErrorMessage(response));
  }

  return (await response.json()) as ResponseBody;
}

export async function postJson<ResponseBody>(url: string, body: unknown) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new ApiError(response.status, await getResponseErrorMessage(response));
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
