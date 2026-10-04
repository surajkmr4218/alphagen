import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useApi, type QueueItem } from "../lib/api";
import { usd } from "../lib/format";
import { Badge } from "./ui/Badge";
import { EmptyState } from "./ui/EmptyState";
import { Skeleton } from "./ui/Skeleton";

/**
 * Owner-only. Lists what is waiting for a decision; the decision itself is made in
 * the DecisionBar under the trail so there is one place to act.
 */
export function ApprovalQueue({ selectedId, onSelect }: { selectedId: string | null | undefined; onSelect: (id: string) => void }) {
  const api = useApi();
  const { data, isLoading } = useQuery({
    queryKey: ["queue"],
    queryFn: () => api<QueueItem[]>("/owner/queue"),
  });

  return (
    <section className="flex flex-col gap-3" aria-labelledby="queue-h">
      <div className="flex items-baseline justify-between">
        <h2 id="queue-h" className="text-[13px] font-medium text-ink">Awaiting your call</h2>
        {data && data.length > 0 && <span className="font-mono text-xs text-accent">{data.length}</span>}
      </div>
      {isLoading ? (
        <Skeleton className="h-16" />
      ) : !data?.length ? (
        <EmptyState>Nothing to approve right now.</EmptyState>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {data.map((q) => {
            const active = q.decision_id === selectedId;
            return (
              <li key={q.decision_id} className="row-enter">
                <button
                  type="button"
                  onClick={() => onSelect(q.decision_id)}
                  aria-current={active ? "true" : undefined}
                  className={`flex w-full items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors duration-150 ${
                    active ? "border-accent/50 bg-inset" : "border-edge bg-inset/40 hover:border-edge-bright hover:bg-inset"
                  }`}
                >
                  <span className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="flex items-center gap-2">
                      <span className="font-mono text-[15px] font-medium text-ink">{q.ticker}</span>
                      {q.hypothesis.size_usd != null && <span className="font-mono text-xs text-muted">{usd(q.hypothesis.size_usd)}</span>}
                      {q.hypothesis.confidence != null && (
                        <span className="font-mono text-xs text-faint">{Math.round(q.hypothesis.confidence * 100)}% conf</span>
                      )}
                    </span>
                    {q.critic_verdict?.verdict && (
                      <span>
                        <Badge tone={q.critic_verdict.verdict === "accept" ? "up" : "down"} glyph={q.critic_verdict.verdict === "accept" ? "check" : "x"}>
                          Critic: {q.critic_verdict.verdict}
                        </Badge>
                      </span>
                    )}
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-faint" aria-hidden />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
