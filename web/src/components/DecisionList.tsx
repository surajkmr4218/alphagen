import type { DecisionSummary } from "../lib/api";
import { relativeTime, signedPct, usd } from "../lib/format";
import { inTab, statusView, TABS, type Tab } from "../lib/status";
import { Badge } from "./ui/Badge";
import { EmptyState } from "./ui/EmptyState";
import { Skeleton } from "./ui/Skeleton";
import { Tabs } from "./ui/Tabs";

const TAB_LABELS: Record<Tab, string> = {
  queue: "Queue",
  approved: "Approved",
  rejected: "Rejected",
  all: "All",
};

interface Props {
  decisions: DecisionSummary[] | undefined;
  isLoading: boolean;
  tab: Tab;
  onTab: (t: Tab) => void;
  selectedId: string | null | undefined;
  onSelect: (id: string) => void;
  canRun: boolean;
}

export function DecisionList({ decisions, isLoading, tab, onTab, selectedId, onSelect, canRun }: Props) {
  const all = decisions ?? [];
  const shown = all.filter((d) => inTab(d, tab));
  const items = TABS.map((t) => ({
    id: t,
    label: TAB_LABELS[t],
    // Only the queue carries a count: it is the one number that asks for action.
    count: t === "queue" ? all.filter((d) => inTab(d, t)).length : undefined,
  }));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-ink">Hypotheses</h2>
        {!isLoading && <span className="font-mono text-xs text-faint">{all.length}</span>}
      </div>
      <Tabs items={items} value={tab} onChange={onTab} label="Filter hypotheses" />

      {isLoading ? (
        <ul className="flex flex-col gap-1" aria-busy>
          {Array.from({ length: 6 }).map((_, i) => (
            <li key={i}><Skeleton className="h-[52px] w-full" /></li>
          ))}
        </ul>
      ) : shown.length === 0 ? (
        <EmptyState>
          {tab === "queue" ? "Nothing waiting for your call."
          : tab === "all" ? (canRun ? "No hypotheses yet. Run a ticker to start." : "No hypotheses yet.")
          : `No ${TAB_LABELS[tab].toLowerCase()} hypotheses.`}
        </EmptyState>
      ) : (
        <ul className="-mx-2 flex flex-col gap-px">
          {shown.map((d) => {
            const st = statusView(d);
            const active = d.decision_id === selectedId;
            const filled = d.entry != null && d.current_price != null;
            return (
              <li key={d.decision_id} className="row-enter">
                <button
                  type="button"
                  aria-current={active ? "true" : undefined}
                  onClick={() => onSelect(d.decision_id)}
                  className={`relative flex w-full flex-col gap-1 rounded-md px-3 py-2 text-left transition-colors duration-150
                    before:absolute before:top-2.5 before:bottom-2.5 before:left-0 before:w-0.5 before:rounded-full before:bg-accent
                    before:origin-center before:transition-transform before:duration-200 before:ease-[var(--ease-out-quart)]
                    ${active ? "bg-inset before:scale-y-100" : "before:scale-y-0 hover:bg-inset/60"}`}
                >
                  <span className="flex w-full items-center justify-between gap-2">
                    <span className="flex items-baseline gap-2">
                      <span className={`font-mono text-[15px] font-medium ${active ? "text-ink" : "text-ink/85"}`}>{d.ticker}</span>
                      {d.size_usd != null && <span className="font-mono text-xs text-muted">{usd(d.size_usd)}</span>}
                    </span>
                    <span className="flex items-center gap-1.5">
                      {d.unrealized_pnl_pct != null && (
                        <Badge tone={d.unrealized_pnl_pct >= 0 ? "up" : "down"}>{signedPct(d.unrealized_pnl_pct)}</Badge>
                      )}
                      <Badge tone={st.tone} glyph={st.glyph} pulse={st.pulse}>{st.label}</Badge>
                    </span>
                  </span>
                  <span className="flex w-full items-center justify-between gap-2 text-xs text-faint">
                    <span>{relativeTime(d.created_at)}</span>
                    {filled && (
                      <span className="font-mono">
                        {usd(d.entry!)} <span className="text-faint/70">to</span> {usd(d.current_price!)}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
