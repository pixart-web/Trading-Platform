import { upstreamURL } from "@/lib/proxy";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };
type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

async function forward(request: Request, context: Context, method: Method) {
  const { path } = await context.params;
  const liveControl = path[0] === "live-control";
  let url: URL;
  try {
    if (liveControl && method !== "GET") {
      const fetchSite = request.headers.get("sec-fetch-site");
      const uiRequest = request.headers.get("x-pa-ui-request");
      if (!["same-origin", "same-site"].includes(fetchSite ?? "") || uiRequest !== "live-control") {
        return Response.json({ detail: "Pedido de controlo inválido." }, { status: 403 });
      }
    }
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
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    };
    if (liveControl) {
      const tokenFile = process.env.PA_CONTROL_PROXY_TOKEN_FILE;
      const token = tokenFile ? readFileSync(tokenFile, "utf8").trim()
        : process.env.PA_CONTROL_PROXY_TOKEN?.trim();
      if (!token || token.length < 32) {
        return Response.json({ detail: "Controlo LIVE não configurado." }, { status: 503 });
      }
      headers["X-PA-Control-Token"] = token;
      headers["X-PA-Actor"] = process.env.PA_OPERATOR_ID ?? "operator";
      headers["X-Correlation-ID"] = randomUUID();
    }
    const response = await fetch(url, {
      method, body, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8000),
      headers,
    });
    if (!response.ok) {
      const status = [404, 409, 422].includes(response.status) ? response.status : 503;
      const detail = liveControl
        ? status === 409 ? "O estado operacional mudou. Atualiza e tenta novamente."
          : status === 422 ? "A ação foi recusada pelos gates do backend."
            : "Controlo LIVE indisponível."
        : status === 409 ? "A lista mudou. Atualiza e tenta novamente."
          : "Dados de mercado indisponíveis.";
      return Response.json({ detail }, { status });
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
