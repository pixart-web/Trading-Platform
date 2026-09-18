import Link from "next/link";
import { MarketWorkspace } from "@/components/market-workspace";
import { recentRange } from "@/lib/market-data";

export const dynamic = "force-dynamic";

export default function Page() {
  return <><Link href="/paper" style={{ display: "block", padding: "0.5rem 1rem" }}>PAPER · execução simulada</Link><MarketWorkspace initialRange={recentRange("1h")} /></>;
}
