import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi, type DecisionSummary, type Me } from "./lib/api";
import { ReasoningTrail } from "./components/ReasoningTrail";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { EvalPanel } from "./components/EvalPanel";

const decisionBadge = (decision: string) =>
  decision === "approved" ? "badge-up" : decision === "rejected" ? "badge-down" : "badge-warn";

export default function Dashboard({ me }: { me: Me }) {
  const api = useApi();
  const { data: decisions } = useQuery({
    queryKey: ["decisions"],
    queryFn: () => api<DecisionSummary[]>("/decisions"),
  });
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? decisions?.[0]?.decision_id; // default to the newest

  return (
    <main className="grid items-start gap-5 p-6 lg:grid-cols-[16rem_1fr_20rem]">
      <section className="panel">
        <h3 className="eyebrow">Hypotheses</h3>
        {!decisions?.length && <p className="text-sm text-faint">No decisions yet.</p>}
        {(decisions ?? []).map((d) => (
          <button
            key={d.decision_id}
            onClick={() => setPicked(d.decision_id)}
            className={`mb-1 flex w-full items-center justify-between gap-2 rounded-[2px] border px-2.5 py-2 text-left font-mono text-sm transition-colors ${
              d.decision_id === selected
                ? "border-edge-bright bg-inset font-semibold text-ink"
                : "border-transparent text-muted hover:bg-inset/60 hover:text-ink"
            }`}
          >
            {d.ticker}
            <span className={`badge ${decisionBadge(d.human_decision)}`}>{d.human_decision}</span>
          </button>
        ))}
      </section>

      {selected ? (
        <ReasoningTrail decisionId={selected} />
      ) : (
        <p className="p-4 text-sm text-faint">Select a hypothesis to see its reasoning trail.</p>
      )}

      <div className="space-y-5">
        <EvalPanel />
        {/* Hidden (not just disabled) for non-owner roles. */}
        {me.role === "owner" && <ApprovalQueue />}
      </div>
    </main>
  );
}