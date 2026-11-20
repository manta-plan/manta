import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getRecordCatalogue, getRecordRevisions, isSecure, recordServerConfig } from "./record-server";

describe("record server", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_RECORD_SERVER", "localhost:8010");
    vi.stubEnv("VITE_RECORD_TOKEN", "devtoken");
    vi.stubGlobal("window", { location: { protocol: "http:", host: "34.51.179.198:8001" } });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  function stubFetch(response: Partial<Response>) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("reads the catalogue with the token", async () => {
    const fetchMock = stubFetch({ ok: true, json: async () => ({ records: [], default: null }) });

    await expect(getRecordCatalogue()).resolves.toEqual({ records: [], default: null });
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8010/api/records", {
      headers: { Authorization: "Bearer devtoken" },
    });
  });

  it("returns a record's revision uuids by name", async () => {
    const fetchMock = stubFetch({
      ok: true,
      json: async () => ({ revisions: { inputs: "1bad4cfd" } }),
    });

    await expect(getRecordRevisions("ac-dc-meshed")).resolves.toEqual({ inputs: "1bad4cfd" });
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8010/api/records/ac-dc-meshed/files");
  });

  it("returns no revisions for a record without any", async () => {
    stubFetch({ ok: true, json: async () => ({ revisions: null }) });

    await expect(getRecordRevisions("plain")).resolves.toEqual({});
  });

  it("explains a refused token", async () => {
    stubFetch({ ok: false, status: 401 });

    await expect(getRecordCatalogue()).rejects.toThrow("The record server refused the token.");
  });

  describe("where the server is", () => {
    it("is the page's own origin when no server is set", async () => {
      vi.stubEnv("VITE_RECORD_SERVER", "");
      const fetchMock = stubFetch({ ok: true, json: async () => ({ records: [], default: null }) });

      expect(recordServerConfig().server).toBe("34.51.179.198:8001");
      await getRecordCatalogue();
      expect(fetchMock.mock.calls[0][0]).toBe("http://34.51.179.198:8001/api/records");
    });

    it("calls a plain-http page's server over http, even on another host", async () => {
      vi.stubEnv("VITE_RECORD_SERVER", "quack.example.org");
      const fetchMock = stubFetch({ ok: true, json: async () => ({ records: [], default: null }) });

      await getRecordCatalogue();
      expect(fetchMock.mock.calls[0][0]).toBe("http://quack.example.org/api/records");
    });

    it("calls an https page's server over https", async () => {
      vi.stubGlobal("window", { location: { protocol: "https:", host: "manta.example.org" } });
      vi.stubEnv("VITE_RECORD_SERVER", "");
      const fetchMock = stubFetch({ ok: true, json: async () => ({ records: [], default: null }) });

      expect(isSecure()).toBe(true);
      await getRecordCatalogue();
      expect(fetchMock.mock.calls[0][0]).toBe("https://manta.example.org/api/records");
    });
  });
});
