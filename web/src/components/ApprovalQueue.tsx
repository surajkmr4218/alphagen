import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi, type QueueItem } from "../lib/api";

// Owner-only: the parent must not render this for public roles (hidden, not disabled).
export function ApprovalQueue() {
  const api = useApi();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["queue"], queryFn: () => api<QueueItem[]>("/owner/queue") });
  const act = useMutation({
    mutationFn: (v: { id: string; action: "approve" | "reject" }) =>
      api(`/owner/${v.action}/${v.id}`, { method: "POST" }),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["queue"] }),
        qc.invalidateQueries({ queryKey: ["decisions"] }),
        qc.invalidateQueries({ queryKey: ["trail"] }),
        qc.invalidateQueries({ queryKey: ["account"] }),
        qc.invalidateQueries({ queryKey: ["eval"] }),
      ]),
  });

  return (
    <section className="panel">
      <h3 className="eyebrow">Approval queue</h3>
      {!data?.length && <p className="text-sm text-faint">No pending approvals.</p>}
      {(data ?? []).map((q) => (
        <div
          key={q.decision_id}
          className="mb-3 rounded-[2px] border border-edge-bright bg-inset p-3 last:mb-0"
        >
          <div className="flex items-baseline justify-between gap-2">
            <b className="font-mono text-sm font-semibold text-ink">{q.ticker}</b>
            <span className="font-mono text-xs tabular-nums text-muted">
              ${q.hypothesis.size_usd}
              {q.hypothesis.confidence != null && <> · conf {(q.hypothesis.confidence * 100).toFixed(0)}%</>}
            </span>
          </div>
          <p className="my-2.5 text-[13px] leading-relaxed text-muted">{q.hypothesis.rationale}</p>
          {/* The critic is advisory — show its take so the human gate decides informed. */}
          {q.critic_verdict?.verdict && (
            <div className="mb-2.5">
              <span className={`badge ${q.critic_verdict.verdict === "accept" ? "badge-up" : "badge-down"}`}>
                critic: {q.critic_verdict.verdict}
              </span>
              {q.critic_verdict.verdict !== "accept" &&
                (q.critic_verdict.reasons ?? []).map((r, i) => (
                  <p key={i} className="mt-1.5 text-xs leading-relaxed text-faint">— {r}</p>
                ))}
            </div>
          )}
          <div className="flex gap-2">
            <button
              className="btn btn-up flex-1"
              disabled={act.isPending}
              onClick={() => act.mutate({ id: q.decision_id, action: "approve" })}
            >
              Approve &amp; place
            </button>
            <button
              className="btn btn-down"
              disabled={act.isPending}
              onClick={() => act.mutate({ id: q.decision_id, action: "reject" })}
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}
