import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useApi, type DecisionSummary, type Me } from "./lib/api";
import { inTab, isLive, type Tab } from "./lib/status";
import { useSelectedDecision } from "./lib/route";
import { useMediaQuery } from "./lib/useMediaQuery";
import { AccountCompact } from "./components/AccountStrip";
import { ApprovalQueue } from "./components/ApprovalQueue";
import { DecisionBar } from "./components/DecisionBar";
import { DecisionList } from "./components/DecisionList";
import { EvalPanel } from "./components/EvalPanel";
import { NewTradeForm } from "./components/NewTradeForm";
import { ReasoningTrail } from "./components/ReasoningTrail";
import { EmptyState } from "./components/ui/EmptyState";

export default function Dashboard({ me }: { me: Me }) {
  const api = useApi();
  const { data: decisions, isLoading } = useQuery({
    queryKey: ["decisions"],
    queryFn: () => api<DecisionSummary[]>("/decisions"),
    refetchInterval: 30_000, // same cadence as the account strip, keeps the P&L fresh
  });
  const [hashId, select] = useSelectedDecision();
  const [tab, setTab] = useState<Tab>("all");
  const wide = useMediaQuery("(min-width: 1024px)");
  const owner = me.role === "owner";

  const all = decisions ?? [];
  const shown = all.filter((d) => inTab(d, tab));
  // Desktop auto-opens the first row; phones show the list until a row is tapped.
  const fallback = shown[0]?.decision_id ?? all[0]?.decision_id ?? null;
  const selected = hashId ?? (wide ? fallback : null);
  const summary = all.find((d) => d.decision_id === selected);
  const live = isLive(summary);
  const showDetail = !wide && selected != null;

  // On desktop, selection replaces history so clicking through rows doesn't pile up entries.
  const pick = (id: string) => select(id, { replace: wide });

  const secondary = (
    <>
      {owner && <ApprovalQueue selectedId={selected} onSelect={pick} />}
      <EvalPanel />
    </>
  );

  return (
    <div className="mx-auto w-full max-w-[1600px] flex-1 lg:grid lg:grid-cols-[20rem_minmax(0,1fr)] xl:grid-cols-[20rem_minmax(0,1fr)_20rem]">
      <aside
        className={`${showDetail ? "hidden" : "flex"} flex-col gap-7 px-4 py-5 lg:sticky lg:top-14 lg:flex lg:h-[calc(100dvh-3.5rem)] lg:overflow-y-auto lg:border-r lg:border-edge lg:bg-surface lg:px-5`}
      >
        <AccountCompact />
        {owner && <NewTradeForm onSelect={pick} />}
        <DecisionList
          decisions={decisions}
          isLoading={isLoading}
          tab={tab}
          onTab={setTab}
          selectedId={selected}
          onSelect={pick}
          canRun={owner}
        />
        <div className="flex flex-col gap-7 border-t border-edge pt-6 xl:hidden">{secondary}</div>
      </aside>

      <section className={`${showDetail ? "flex" : "hidden"} min-w-0 flex-col px-4 py-5 lg:flex lg:px-8 lg:py-6`}>
        {showDetail && (
          <button
            type="button"
            onClick={() => select(null)}
            className="mb-4 -ml-2 inline-flex h-10 items-center gap-1.5 self-start rounded-md px-2 text-sm text-muted transition-colors hover:text-ink"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Hypotheses
          </button>
        )}
        {selected ? (
          <div key={selected} className={`flex flex-1 flex-col ${showDetail ? "animate-slide-in-right" : ""}`}>
            <ReasoningTrail decisionId={selected} summary={summary} live={live} />
            {owner && <DecisionBar decisionId={selected} />}
          </div>
        ) : (
          <EmptyState className="my-auto">Select a hypothesis to read its reasoning trail.</EmptyState>
        )}
      </section>

      <aside className="hidden xl:sticky xl:top-14 xl:flex xl:h-[calc(100dvh-3.5rem)] xl:flex-col xl:gap-8 xl:overflow-y-auto xl:border-l xl:border-edge xl:bg-surface xl:px-5 xl:py-5">
        {secondary}
      </aside>
    </div>
  );
}
