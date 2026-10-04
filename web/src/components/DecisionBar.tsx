import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useApi, type QueueItem } from "../lib/api";
import { usd } from "../lib/format";
import { Button } from "./ui/Button";
import { Toast, type ToastData } from "./ui/Toast";

/**
 * Owner-only. Sticks to the bottom of the trail while the selected decision is
 * waiting for a human, so the approve/reject buttons sit next to the evidence.
 */
export function DecisionBar({ decisionId }: { decisionId: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const [toast, setToast] = useState<ToastData | null>(null);
  const { data: queue } = useQuery({
    queryKey: ["queue"],
    queryFn: () => api<QueueItem[]>("/owner/queue"),
  });
  const item = queue?.find((q) => q.decision_id === decisionId);

  const act = useMutation({
    mutationFn: (v: { id: string; action: "approve" | "reject" }) =>
      api(`/owner/${v.action}/${v.id}`, { method: "POST" }),
    onSuccess: (_r, v) =>
      setToast({ id: Date.now(), message: v.action === "approve" ? "Order placed" : "Hypothesis rejected", tone: v.action === "approve" ? "up" : "neutral" }),
    // onSettled, not onSuccess: an approve can flip human_decision in the database and then
    // fail during order execution, so the UI must refetch on error too.
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["queue"] }),
        qc.invalidateQueries({ queryKey: ["decisions"] }),
        qc.invalidateQueries({ queryKey: ["trail"] }),
        qc.invalidateQueries({ queryKey: ["account"] }),
        qc.invalidateQueries({ queryKey: ["eval"] }),
      ]),
  });

  const pendingAction = act.isPending ? act.variables?.action : null;

  return (
    <>
      {item && (
        <div className="sticky bottom-0 z-20 -mx-4 mt-6 border-t border-edge bg-surface px-4 pt-3 shadow-[0_-12px_24px_rgba(11,15,20,0.6)] safe-bottom lg:-mx-8 lg:px-8 animate-rail-in">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-[13px] font-medium text-ink">
                Buy {item.ticker}{item.hypothesis.size_usd != null && <> for {usd(item.hypothesis.size_usd)}</>}?
              </span>
              <span className="text-xs text-muted">
                {act.isPending && pendingAction === "approve"
                  ? "Placing the order with Robinhood. This can take about 30 seconds."
                  : act.isError
                    ? <span role="alert" className="text-down">Action failed: {act.error instanceof Error ? act.error.message : String(act.error)}. Check the order stage above for its actual state.</span>
                    : "The pipeline paused here. Nothing is sent to the broker until you approve."}
              </span>
            </div>
            <div className="flex w-full gap-2 sm:w-auto">
              <Button
                variant="reject"
                className="flex-1 sm:flex-none"
                disabled={act.isPending}
                loading={pendingAction === "reject"}
                icon={<X className="h-4 w-4" aria-hidden />}
                onClick={() => act.mutate({ id: decisionId, action: "reject" })}
              >
                Reject
              </Button>
              <Button
                variant="approve"
                className="flex-1 sm:flex-none"
                disabled={act.isPending}
                loading={pendingAction === "approve"}
                icon={<Check className="h-4 w-4" aria-hidden />}
                onClick={() => act.mutate({ id: decisionId, action: "approve" })}
              >
                Approve &amp; place
              </Button>
            </div>
          </div>
        </div>
      )}
      <Toast toast={toast} onDone={() => setToast(null)} />
    </>
  );
}
