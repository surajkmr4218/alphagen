import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi, type DecisionSummary, type Me } from "./lib/api";
import { AccountBar } from "./components/AccountBar";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { EvalPanel } from "./components/EvalPanel";
import { NewTradeForm } from "./components/NewTradeForm";
import { ReasoningTrail } from "./components/ReasoningTrail";

const decisionBadge = (decision: string) =>
  decision === "approved" ? "badge-up"
  : decision === "rejected" || decision === "failed" ? "badge-down"
  : "badge-warn";

// "approved" records the human decision — check-twice can block the order.
// Once an order row has a real status, show what actually happened to it.
const statusBadge = (d: DecisionSummary): { label: string; cls: string } => {
  if (d.human_decision === "approved" && d.order_status && d.order_status !== "pending") {
    if (d.order_status === "filled") return { label: "filled", cls: "badge-up" };
    if (d.order_status === "rejected") return { label: "blocked", cls: "badge-down" };
    return { label: "submitted", cls: "badge-up" }; // queued/confirmed/partially_filled
  }
  return { label: d.human_decision, cls: decisionBadge(d.human_decision) };
};

const TABS = ["queue", "approved", "rejected", "all"] as const;
type Tab = (typeof TABS)[number];

const inTab = (d: DecisionSummary, tab: Tab) =>
  tab === "all" ? true
  : tab === "queue" ? (d.human_decision === "pending" && d.passed) || d.human_decision === "running"
  : tab === "approved" ? d.human_decision === "approved"
  : d.human_decision === "rejected" || d.human_decision === "failed";

const pct = (v: number) => `${v > 0 ? "+" : ""}${v}%`;

export default function Dashboard({ me }: { me: Me }) {
  const api = useApi();
  const { data: decisions } = useQuery({
    queryKey: ["decisions"],
    queryFn: () => api<DecisionSummary[]>("/decisions"),
    refetchInterval: 30_000, // same cadence as the account bar — keeps the P&L diff fresh
  });
  const [picked, setPicked] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("all");

  const shown = (decisions ?? []).filter((d) => inTab(d, tab));
  const selected = picked ?? shown[0]?.decision_id ?? decisions?.[0]?.decision_id;

  // The open trail should poll only while its decision can still change: the pipeline is
  // running, or an approved order hasn't reached a terminal fill/reject yet.
  const sel = (decisions ?? []).find((d) => d.decision_id === selected);
  const live =
    sel != null &&
    (sel.human_decision === "running" ||
      (sel.human_decision === "approved" &&
        sel.order_status != null &&
        !["filled", "rejected"].includes(sel.order_status)));

  return (
    <main className="space-y-5 p-6">
      <AccountBar />
      <div className="grid items-start gap-5 lg:grid-cols-[18rem_1fr_20rem]">
        <section className="panel">
          <h3 className="eyebrow">Hypotheses</h3>
          <div className="mb-2 flex gap-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-[2px] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider transition-colors ${
                  t === tab ? "bg-inset text-ink" : "text-faint hover:text-muted"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          {!shown.length && <p className="text-sm text-faint">No decisions here yet.</p>}
          {shown.map((d) => (
            <button
              key={d.decision_id}
              onClick={() => setPicked(d.decision_id)}
              className={`mb-1 flex w-full items-center justify-between gap-2 rounded-[2px] border px-2.5 py-2 text-left font-mono text-sm transition-colors ${
                d.decision_id === selected
                  ? "border-edge-bright bg-inset font-semibold text-ink"
                  : "border-transparent text-muted hover:bg-inset/60 hover:text-ink"
              }`}
            >
              <span className="flex items-baseline gap-2">
                {d.ticker}
                {d.size_usd != null && (
                  <span className="text-xs tabular-nums text-faint">${d.size_usd}</span>
                )}
              </span>
              <span className="flex items-center gap-1.5">
                {d.unrealized_pnl_pct != null && (
                  <span className={`badge ${d.unrealized_pnl_pct >= 0 ? "badge-up" : "badge-down"}`}>
                    {pct(d.unrealized_pnl_pct)}
                  </span>
                )}
                <span className={`badge ${statusBadge(d).cls}`}>
                  {d.human_decision === "running" ? (
                    <span className="animate-pulse">running</span>
                  ) : (
                    statusBadge(d).label
                  )}
                </span>
              </span>
            </button>
          ))}
        </section>

        {selected ? (
          <ReasoningTrail decisionId={selected} live={live} />
        ) : (
          <p className="p-4 text-sm text-faint">Select a hypothesis to see its reasoning trail.</p>
        )}

        <div className="space-y-5">
          {/* Hidden (not just disabled) for non-owner roles. */}
          {me.role === "owner" && <NewTradeForm onSelect={setPicked} />}
          <EvalPanel />
          {me.role === "owner" && <ApprovalQueue />}
        </div>
      </div>
    </main>
  );
}
