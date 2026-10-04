import { useQuery } from "@tanstack/react-query";
import { useApi, type EvalSummary } from "../lib/api";
import { ratioPct } from "../lib/format";
import { Skeleton } from "./ui/Skeleton";
import { Stat } from "./ui/Stat";

const signTone = (v: number | null) => (v == null ? "ink" : v > 0 ? "up" : v < 0 ? "down" : "ink");

/** Realised performance from reconciled outcomes, measured against SPY. */
export function EvalPanel() {
  const api = useApi();
  const { data: s, isLoading } = useQuery({
    queryKey: ["eval"],
    queryFn: () => api<EvalSummary>("/eval/summary"),
  });

  return (
    <section className="flex flex-col gap-3" aria-labelledby="perf-h">
      <h2 id="perf-h" className="text-[13px] font-medium text-ink">Performance</h2>
      {isLoading || !s ? (
        <div className="grid grid-cols-3 gap-3 lg:grid-cols-2">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-11" />)}
        </div>
      ) : (
        <dl className="grid grid-cols-3 gap-x-3 gap-y-4 lg:grid-cols-2">
          <Stat label="Resolved trades" value={s.n_resolved} />
          <Stat label="Awaiting horizon" value={s.n_pending} />
          <Stat label="Hit rate" value={ratioPct(s.hit_rate)} tone={signTone(s.hit_rate == null ? null : s.hit_rate - 0.5)} />
          <Stat label="Avg return" value={ratioPct(s.avg_return)} tone={signTone(s.avg_return)} />
          <Stat label="Avg excess vs SPY" value={ratioPct(s.avg_excess_vs_spy)} tone={signTone(s.avg_excess_vs_spy)} />
        </dl>
      )}
    </section>
  );
}
