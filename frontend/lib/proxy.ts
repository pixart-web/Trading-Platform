/** Fixed read-only upstream. No client-controlled host, credentials, redirects or arbitrary paths. */
export function upstreamURL(parts: string[], search: URLSearchParams, base: string): URL {
  const id = /^[A-Za-z0-9_.:-]{1,128}$/;
  const allowed = (parts.length === 1 && ["assets", "markets"].includes(parts[0]))
    || (parts.length === 2 && parts[0] === "assets" && id.test(parts[1]))
    || (parts.length === 3 && parts[0] === "markets" && id.test(parts[1]) && parts[2] === "candles");
  if (!allowed || parts.some(part => part === "." || part === "..")) throw new Error("Unsupported resource");
  const root = new URL(base);
  if (!["http:", "https:"].includes(root.protocol) || root.username || root.password
    || root.pathname !== "/" || root.search || root.hash) throw new Error("Invalid upstream origin");
  const result = new URL("/api/v1/" + parts.map(encodeURIComponent).join("/"), root);
  for (const key of ["q", "asset_type", "limit", "offset", "timeframe", "start", "end"]) {
    const value = search.get(key);
    if (value !== null) {
      if (value.length > 256) throw new Error("Oversized query");
      result.searchParams.set(key, value);
    }
  }
  return result;
}
