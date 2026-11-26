import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearSession, getValidAccessToken, refreshAccessToken } from "../../features/auth/session";
import { ApiError, getJson, postStream } from "../manta";

vi.mock("../../features/auth/session", () => ({
  clearSession: vi.fn(),
  getValidAccessToken: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

const mockedGetValidAccessToken = vi.mocked(getValidAccessToken);
const mockedRefreshAccessToken = vi.mocked(refreshAccessToken);
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  mockedGetValidAccessToken.mockResolvedValue("token-1");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function sentHeaders(call: number) {
  return new Headers(fetchMock.mock.calls[call][1]?.headers);
}

describe("postStream", () => {
  it("posts JSON as the signed-in user and returns the response unread", async () => {
    const response = new Response("event: done\ndata: {}\n\n");
    fetchMock.mockResolvedValue(response);
    const { signal } = new AbortController();

    await expect(postStream("/v1/chat/x", { content: "Hi" }, signal)).resolves.toBe(response);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/v1/chat/x");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"content":"Hi"}');
    expect(init?.signal).toBe(signal);
    expect(sentHeaders(0).get("Authorization")).toBe("Bearer token-1");
    expect(sentHeaders(0).get("Content-Type")).toBe("application/json");
    expect(sentHeaders(0).get("Accept")).toBe("text/event-stream");
    expect(response.bodyUsed).toBe(false);
  });

  it("refreshes the token and sends again on a 401, before any body is read", async () => {
    const response = new Response("event: done\ndata: {}\n\n");
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }));
    fetchMock.mockResolvedValueOnce(response);
    mockedRefreshAccessToken.mockResolvedValue("token-2");

    await expect(postStream("/v1/chat/x", { content: "Hi" })).resolves.toBe(response);

    expect(mockedRefreshAccessToken).toHaveBeenCalledWith("token-1");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(sentHeaders(1).get("Authorization")).toBe("Bearer token-2");
    expect(fetchMock.mock.calls[1][1]?.body).toBe('{"content":"Hi"}');
    expect(response.bodyUsed).toBe(false);
    expect(clearSession).not.toHaveBeenCalled();
  });

  it("ends the session when the request is still refused after a refresh", async () => {
    fetchMock.mockImplementation(async () => new Response(null, { status: 401 }));
    mockedRefreshAccessToken.mockResolvedValue("token-2");

    await expect(postStream("/v1/chat/x", {})).rejects.toMatchObject({ status: 401 });
    expect(clearSession).toHaveBeenCalledTimes(1);
  });

  it("throws the server's reason and its Retry-After on a 429", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        { detail: "Daily message limit reached" },
        { status: 429, headers: { "Retry-After": "30" } },
      ),
    );

    const failure = await postStream("/v1/chat/x", {}).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      status: 429,
      message: "Daily message limit reached",
      retryAfterSeconds: 30,
    });
  });

  it.each(["daily_limit", "concurrency_limit"])(
    "reads the code and message of a 429 detail: %s",
    async (code) => {
      fetchMock.mockResolvedValue(
        Response.json(
          { detail: { code, message: "Try again later" } },
          { status: 429, headers: { "Retry-After": "5" } },
        ),
      );

      await expect(postStream("/v1/chat/x", {})).rejects.toMatchObject({
        status: 429,
        code,
        message: "Try again later",
        retryAfterSeconds: 5,
      });
    },
  );

  it("has no code for a detail that is plain text or a list", async () => {
    fetchMock.mockResolvedValueOnce(Response.json({ detail: "Not Found" }, { status: 404 }));
    fetchMock.mockResolvedValueOnce(
      Response.json(
        { detail: [{ msg: "field required" }] },
        { status: 422, statusText: "Unprocessable Entity" },
      ),
    );

    await expect(postStream("/v1/chat/x", {})).rejects.toMatchObject({
      code: null,
      message: "Not Found",
    });
    await expect(postStream("/v1/chat/x", {})).rejects.toMatchObject({
      code: null,
      message: "Unprocessable Entity",
    });
  });

  it("reads a Retry-After given as a date", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-25T10:00:00Z"));
    fetchMock.mockResolvedValue(
      new Response(null, {
        status: 429,
        headers: { "Retry-After": "Wed, 25 Nov 2026 10:00:45 GMT" },
      }),
    );

    await expect(postStream("/v1/chat/x", {})).rejects.toMatchObject({ retryAfterSeconds: 45 });
  });

  it.each([
    [404, undefined],
    [422, "soon"],
  ])("has no wait for a %i with Retry-After %s", async (status, retryAfter) => {
    fetchMock.mockResolvedValue(
      new Response(null, {
        status,
        headers: retryAfter === undefined ? {} : { "Retry-After": retryAfter },
      }),
    );

    await expect(postStream("/v1/chat/x", {})).rejects.toMatchObject({
      status,
      retryAfterSeconds: null,
    });
  });
});

describe("getJson", () => {
  it("still parses the body of a successful response", async () => {
    fetchMock.mockResolvedValue(Response.json({ enabled: true }));

    await expect(getJson("/v1/chat/status")).resolves.toEqual({ enabled: true });
    expect(sentHeaders(0).get("Authorization")).toBe("Bearer token-1");
  });

  it("still refreshes once on a 401", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }));
    fetchMock.mockResolvedValueOnce(Response.json({ ok: true }));
    mockedRefreshAccessToken.mockResolvedValue("token-2");

    await expect(getJson("/v1/runs")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
