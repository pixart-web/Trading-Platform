import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "../app/api/market-data/[...path]/route";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
describe("gateway route", () => {
  it("forwards successful read responses without caching", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json([]));
    vi.stubGlobal("fetch", fetcher);
    const response = await GET(new Request("http://localhost/api/market-data/markets?q=BTC"),
      { params: Promise.resolve({ path: ["markets"] }) });
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.json()).toEqual([]);
    expect(fetcher.mock.calls[0][0].pathname).toBe("/api/v1/markets");
    expect(fetcher.mock.calls[0][0].search).toBe("?q=BTC");
  });
  it.each([404, 422, 500])("sanitizes backend errors (%s)", async status => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ secret: "private" }, { status })));
    const response = await GET(new Request("http://localhost"), { params: Promise.resolve({ path: ["assets"] }) });
    expect(response.status).toBe(status === 500 ? 503 : status);
    expect(await response.text()).not.toContain("private");
  });
  it("handles unreachable services", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("private service address")));
    const response = await GET(new Request("http://localhost"), { params: Promise.resolve({ path: ["markets"] }) });
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("private");
  });
  it("rejects unsupported resources without connecting", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const response = await GET(new Request("http://localhost"), { params: Promise.resolve({ path: ["orders"] }) });
    expect(response.status).toBe(400);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
