import { upstreamURL } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  let url: URL;
  try {
    url = upstreamURL(path, new URL(request.url).searchParams,
      process.env.PA_API_BASE_URL ?? "http://127.0.0.1:8000");
  } catch {
    return Response.json({ detail: "Recurso indisponível." }, { status: 400 });
  }
  try {
    const response = await fetch(url, {
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8000),
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      const status = [404, 422].includes(response.status) ? response.status : 503;
      return Response.json({ detail: "Dados de mercado indisponíveis." }, { status });
    }
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ detail: "Serviço de dados indisponível." }, { status: 503 });
  }
}
