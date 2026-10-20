export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const base = new URL(process.env.PA_API_BASE_URL ?? "http://127.0.0.1:8000");
    if (!["http:", "https:"].includes(base.protocol) || base.username || base.password
      || base.pathname !== "/" || base.search || base.hash) {
      return Response.json({ status: "unavailable", detail: "Invalid API origin." }, { status: 503 });
    }
    const response = await fetch(new URL("/health/ready", base), {
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000),
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return Response.json({ status: "unavailable" }, { status: 503 });
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ status: "unavailable", detail: "API readiness unavailable." }, { status: 503 });
  }
}
