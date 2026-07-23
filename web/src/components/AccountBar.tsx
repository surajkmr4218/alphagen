import { useQuery } from "@tanstack/react-query";
import { useApi, type AccountSnapshot } from "../lib/api";

// Intentional use of == instead of === to check for undefined and null below
const usd = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("en-US", { style: "currency", currency: "USD" });

// Full-width status strip above the dashboard grid.  
export function AccountBar() {
  const api = useApi();
  const { data } = useQuery({
    queryKey: ["account"],
    queryFn: () => api<AccountSnapshot>("/account"),
    refetchInterval: 30_000,
  });

  return (
    <section className="panel flex flex-wrap items-baseline gap-x-8 gap-y-2">
      <h3 className="eyebrow mb-0 mr-2">Account</h3>
      <div className="flex items-baseline gap-2.5">
        <span className="font-mono text-2xl font-semibold tabular-nums text-ink">
          {usd(data?.total_equity)}
        </span>
        <span className="text-xs text-faint">total equity</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-sm tabular-nums text-muted">{usd(data?.cash)}</span>
        <span className="text-xs text-faint">cash</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-sm tabular-nums text-muted">
          {usd(data?.buying_power)}
        </span>
        <span className="text-xs text-faint">buying power</span>
      </div>
      {data && (
        <span
          className={`badge ml-auto ${data.stale ? "badge-warn" : "badge-up"}`}
          title={data.stale ? "Broker unreachable — showing last-known values" : "Live snapshot"}
        >
          <span
            className={`mr-1 inline-block h-1.5 w-1.5 rounded-full ${
              data.stale ? "bg-warn" : "animate-pulse bg-up"
            }`}
          />
          {data.stale ? "stale" : "live"}
        </span>
      )}
    </section>
  );
}
