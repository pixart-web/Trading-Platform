/** Fixed local upstream. Paths, methods and queries are explicitly allowlisted. */
export function upstreamURL(
  parts: string[], search: URLSearchParams, base: string, method = "GET",
): URL {
  const id = /^[A-Za-z0-9_.:-]{1,128}$/;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const marketRead = (parts.length === 1 && ["assets", "markets"].includes(parts[0]))
    || (parts.length === 2 && parts[0] === "assets" && id.test(parts[1]))
    || (parts.length === 3 && parts[0] === "markets" && id.test(parts[1])
      && ["analysis", "candles", "zones"].includes(parts[2]));
  const scanCollection = parts.length === 1 && parts[0] === "scans";
  const scanDetail = parts.length === 2 && parts[0] === "scans" && uuid.test(parts[1]);
  const watchlistId = parts[0] === "watchlists" && parts.length > 1 && uuid.test(parts[1]);
  const watchlistCollection = parts.length === 1 && parts[0] === "watchlists";
  const watchlistDetail = watchlistId && parts.length === 2;
  const watchlistMember = watchlistId && parts.length === 4 && parts[2] === "markets"
    && id.test(parts[3]);
  const watchlistSnapshot = watchlistId && parts.length === 3 && parts[2] === "snapshots";
  const watchlistLatest = watchlistId && parts.length === 4 && parts[2] === "snapshots"
    && parts[3] === "latest";
  const watchlistAlerts = watchlistId && parts.length === 3 && parts[2] === "alerts";
  const allowed = (method === "GET" && (marketRead || scanCollection || scanDetail || watchlistCollection || watchlistDetail
      || watchlistLatest || watchlistAlerts))
    || (method === "POST" && (scanCollection || watchlistCollection || watchlistSnapshot))
    || (method === "PATCH" && watchlistDetail)
    || (method === "PUT" && watchlistMember)
    || (method === "DELETE" && watchlistMember);
  if (!allowed || parts.some(part => part === "." || part === "..")) {
    throw new Error("Unsupported resource");
  }
  const root = new URL(base);
  if (!["http:", "https:"].includes(root.protocol) || root.username || root.password
    || root.pathname !== "/" || root.search || root.hash) throw new Error("Invalid upstream origin");
  const result = new URL("/api/v1/" + parts.map(encodeURIComponent).join("/"), root);
  for (const key of ["q", "asset_type", "limit", "offset", "timeframe", "start", "end",
    "as_of", "expected_revision"]) {
    const value = search.get(key);
    if (value !== null) {
      if (value.length > 256) throw new Error("Oversized query");
      result.searchParams.set(key, value);
    }
  }
  return result;
}
