import { upstreamURL } from "@/lib/proxy";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };
type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

async function forward(request: Request, context: Context, method: Method) {
  const { path } = await context.params;
  let url: URL;
  try {
    url = upstreamURL(path, new URL(request.url).searchParams,
      process.env.PA_API_BASE_URL ?? "http://127.0.0.1:8000", method);
  } catch {
    return Response.json({ detail: "Recurso indisponível." }, { status: 400 });
  }
  try {
    const length = Number(request.headers.get("content-length") ?? "0");
    if (!Number.isFinite(length) || length > 8192) {
      return Response.json({ detail: "Pedido demasiado grande." }, { status: 413 });
    }
    const body = method === "GET" || method === "DELETE" ? undefined : await request.text();
    if (body && body.length > 8192) {
      return Response.json({ detail: "Pedido demasiado grande." }, { status: 413 });
    }
    const response = await fetch(url, {
      method, body, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8000),
      headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
    });
    if (!response.ok) {
      const status = [404, 409, 422].includes(response.status) ? response.status : 503;
      return Response.json({ detail: status === 409 ? "A lista mudou. Atualiza e tenta novamente."
        : "Dados de mercado indisponíveis." }, { status });
    }
    return Response.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ detail: "Serviço de dados indisponível." }, { status: 503 });
  }
}

export function GET(request: Request, context: Context) { return forward(request, context, "GET"); }
export function POST(request: Request, context: Context) { return forward(request, context, "POST"); }
export function PUT(request: Request, context: Context) { return forward(request, context, "PUT"); }
export function PATCH(request: Request, context: Context) { return forward(request, context, "PATCH"); }
export function DELETE(request: Request, context: Context) { return forward(request, context, "DELETE"); }