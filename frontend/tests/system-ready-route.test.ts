import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "../app/api/system/ready/route";

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe("system readiness gateway", () => {
  it("forwards only the fixed readiness path without caching", async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ status: "ready" }));
    vi.stubGlobal("fetch", fetcher);
    vi.stubEnv("PA_API_BASE_URL", "http://api.internal:8000");
    const response = await GET();
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(fetcher.mock.calls[0][0].href).toBe("http://api.internal:8000/health/ready");
  });

  it("fails closed for an invalid configured origin", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    vi.stubEnv("PA_API_BASE_URL", "http://api.internal:8000/unapproved-base");
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("unapproved-base");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("sanitizes failed upstream readiness", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ private: "detail" }, { status: 500 })));
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("detail");
  });

  it("sanitizes transport failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("private host")));
    const response = await GET();
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("private host");
  });
});
