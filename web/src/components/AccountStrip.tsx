import { useQuery } from "@tanstack/react-query";
import { useApi, type AccountSnapshot } from "../lib/api";
import { usd, usdOrDash } from "../lib/format";
import { Badge } from "./ui/Badge";
import { FlashValue } from "./ui/FlashValue";
import { Skeleton } from "./ui/Skeleton";
import { Stat } from "./ui/Stat";

function useAccount() {
  const api = useApi();
  return useQuery({
    queryKey: ["account"],
    queryFn: () => api<AccountSnapshot>("/account"),
    refetchInterval: 30_000,
  });
}

function LiveBadge({ stale }: { stale: boolean }) {
  return (
    <Badge
      tone={stale ? "warn" : "up"}
      glyph="dot"
      pulse={!stale}
      title={stale ? "Broker unreachable. Showing last-known values." : "Live broker snapshot"}
    >
      {stale ? "Stale" : "Live"}
    </Badge>
  );
}

/** Header variant: equity always, cash and buying power from md up. */
export function AccountHeader() {
  const { data, isLoading, isError } = useAccount();
  if (isLoading) return <Skeleton className="h-6 w-28" />;
  if (isError || !data) return null; // profile errors and the link gate already explain themselves
  return (
    <div className="flex min-w-0 items-center gap-4 md:gap-6">
      <div className="flex items-baseline gap-2">
        <FlashValue value={data?.total_equity} format={usd} className="text-base font-medium text-ink md:text-lg" />
        <span className="hidden text-xs text-muted sm:inline">equity</span>
      </div>
      <div className="hidden items-baseline gap-2 md:flex">
        <span className="font-mono text-sm text-muted">{usdOrDash(data?.cash)}</span>
        <span className="text-xs text-faint">cash</span>
      </div>
      <div className="hidden items-baseline gap-2 md:flex">
        <span className="font-mono text-sm text-muted">{usdOrDash(data?.buying_power)}</span>
        <span className="text-xs text-faint">buying power</span>
      </div>
      <div className="hidden md:block"><LiveBadge stale={data.stale} /></div>
    </div>
  );
}

/** Compact variant for phones: the figures the header had to drop. */
export function AccountCompact() {
  const { data, isLoading } = useAccount();
  return (
    <div className="flex items-end justify-between gap-4 md:hidden">
      {isLoading ? (
        <Skeleton className="h-9 w-40" />
      ) : (
        <div className="flex gap-6">
          <Stat label="Cash" value={usdOrDash(data?.cash)} size="sm" />
          <Stat label="Buying power" value={usdOrDash(data?.buying_power)} size="sm" />
        </div>
      )}
      {data && <LiveBadge stale={data.stale} />}
    </div>
  );
}
