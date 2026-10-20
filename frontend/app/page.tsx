import { MarketWorkspace } from "@/components/market-workspace";
import { recentRange } from "@/lib/market-data";

export const dynamic = "force-dynamic";

export default function Page() {
  return <MarketWorkspace initialRange={recentRange("1h")} />;
}
