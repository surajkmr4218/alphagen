import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi, type DecisionSummary, type Me } from "./lib/api";
import { ReasoningTrail } from "./components/ReasoningTrail";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { EvalPanel } from "./components/EvalPanel";

export default function Dashboard({ me }: { me: Me }) {
  const api = useApi();
  const { data: decisions } = useQuery({
    queryKey: ["decisions"],
    queryFn: () => api<DecisionSummary[]>("/decisions"),
  });
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? decisions?.[0]?.decision_id; // default to the newest

  return (
    <main className="grid items-start gap-4 p-6 lg:grid-cols-[16rem_1fr_20rem]">
      <section className="rounded-lg border bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold text-gray-500">Hypotheses</h3>
        {!decisions?.length && <p className="text-sm text-gray-400">No decisions yet.</p>}
        {(decisions ?? []).map((d) => (
          <button
            key={d.decision_id}
            onClick={() => setPicked(d.decision_id)}
            className={`mb-1 block w-full rounded px-2 py-1 text-left text-sm hover:bg-gray-100 ${
              d.decision_id === selected ? "bg-gray-100 font-semibold" : ""
            }`}
          >
            {d.ticker}
            <span className="float-right text-xs text-gray-400">{d.human_decision}</span>
          </button>
        ))}
      </section>

      {selected ? (
        <ReasoningTrail decisionId={selected} />
      ) : (
        <p className="p-4 text-gray-400">Select a hypothesis to see its reasoning trail.</p>
      )}

      <div className="space-y-4">
        <EvalPanel />
        {/* Hidden (not just disabled) for non-owner roles. */}
        {me.role === "owner" && <ApprovalQueue />}
      </div>
    </main>
  );
}
