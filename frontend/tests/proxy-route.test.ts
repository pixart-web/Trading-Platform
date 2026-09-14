import { afterEach, describe, expect, it, vi } from "vitest";
import { DELETE, GET, POST, PUT } from "../app/api/market-data/[...path]/route";

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
  it("allows only the Analyze read route and its bounded query keys", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ status: "UNAVAILABLE" }));
    vi.stubGlobal("fetch", fetcher);
    const response = await GET(new Request("http://localhost/api/market-data/markets/test/analysis?timeframe=1h&as_of=2025-01-01T00%3A00%3A00Z&secret=no"),
      { params: Promise.resolve({ path: ["markets", "test", "analysis"] }) });
    expect(response.status).toBe(200);
    expect(fetcher.mock.calls[0][0].pathname).toBe("/api/v1/markets/test/analysis");
    expect(fetcher.mock.calls[0][0].searchParams.has("as_of")).toBe(true);
    expect(fetcher.mock.calls[0][0].searchParams.has("secret")).toBe(false);
  });
  it("forwards only bounded watchlist mutations", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(Response.json({ revision: 2 })));
    vi.stubGlobal("fetch", fetcher);
    const context = { params: Promise.resolve({ path: ["watchlists", "00000000-0000-0000-0000-000000000001", "markets", "test-market"] }) };
    const put = await PUT(new Request("http://localhost/api/market-data/watchlists/id/markets/test-market", {
      method: "PUT", body: JSON.stringify({ expected_revision: 1 }),
    }), context);
    expect(put.status).toBe(200);
    expect(fetcher.mock.calls[0][1].method).toBe("PUT");
    expect(fetcher.mock.calls[0][1].body).toContain("expected_revision");
    const removed = await DELETE(new Request("http://localhost/api/market-data/watchlists/id/markets/test-market?expected_revision=2", {
      method: "DELETE",
    }), context);
    expect(removed.status).toBe(200);
    expect(fetcher.mock.calls[1][0].search).toBe("?expected_revision=2");
  });
  it("rejects wrong methods and oversized mutation bodies", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const context = { params: Promise.resolve({ path: ["watchlists"] }) };
    const wrong = await PUT(new Request("http://localhost", { method: "PUT", body: "{}" }), context);
    expect(wrong.status).toBe(400);
    const oversized = await POST(new Request("http://localhost", {
      method: "POST", body: "x".repeat(8193),
    }), context);
    expect(oversized.status).toBe(413);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("rejects unsupported resources without connecting", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const response = await GET(new Request("http://localhost"), { params: Promise.resolve({ path: ["orders"] }) });
    expect(response.status).toBe(400);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("forwards scanner creation and bounded reads", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(Response.json({ status: "NO_MATCHES" })));
    vi.stubGlobal("fetch", fetcher);
    const created = await POST(new Request("http://localhost/api/market-data/scans", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scan_id: "test" }),
    }), { params: Promise.resolve({ path: ["scans"] }) });
    expect(created.status).toBe(200);
    expect(fetcher.mock.calls[0][0].pathname).toBe("/api/v1/scans");
    expect(fetcher.mock.calls[0][1].method).toBe("POST");
    const read = await GET(new Request("http://localhost/api/market-data/scans?limit=20&secret=no"),
      { params: Promise.resolve({ path: ["scans"] }) });
    expect(read.status).toBe(200);
    expect(fetcher.mock.calls[1][0].search).toBe("?limit=20");
  });
});
