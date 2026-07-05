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
      ]),
  });

  return (
    <section className="rounded-lg border bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold text-gray-500">Approval queue</h3>
      {!data?.length && <p className="text-sm text-gray-400">No pending approvals.</p>}
      {(data ?? []).map((q) => (
        <div key={q.decision_id} className="mb-3 rounded border p-3">
          <div className="flex justify-between">
            <b>{q.ticker}</b>
            <span className="text-sm text-gray-500">
              ${q.hypothesis.size_usd}
              {q.hypothesis.confidence != null && <> · conf {(q.hypothesis.confidence * 100).toFixed(0)}%</>}
            </span>
          </div>
          <p className="my-2 text-sm text-gray-600">{q.hypothesis.rationale}</p>
          <div className="flex gap-2">
            <button
              className="rounded bg-emerald-600 px-3 py-1 text-sm text-white disabled:opacity-50"
              disabled={act.isPending}
              onClick={() => act.mutate({ id: q.decision_id, action: "approve" })}
            >
              Approve &amp; place
            </button>
            <button
              className="rounded bg-rose-700 px-3 py-1 text-sm text-white disabled:opacity-50"
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
