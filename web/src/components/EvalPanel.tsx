import { useQuery } from "@tanstack/react-query";
import { useApi, type EvalSummary } from "../lib/api";

const pct = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

// Live performance computed from resolved Outcomes (reconciliation job, Session 5).
export function EvalPanel() {
  const api = useApi();
  const { data: s } = useQuery({ queryKey: ["eval"], queryFn: () => api<EvalSummary>("/eval/summary") });

  const rows: [string, string][] = s
    ? [
        ["Resolved trades", String(s.n_resolved)],
        ["Awaiting horizon", String(s.n_pending)],
        ["Hit rate", pct(s.hit_rate)],
        ["Avg return", pct(s.avg_return)],
        ["Avg excess vs SPY", pct(s.avg_excess_vs_spy)],
      ]
    : [];

  return (
    <section className="panel">
      <h3 className="eyebrow">Performance</h3>
      {!s ? (
        <p className="text-sm text-faint">Loading…</p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-b border-edge/70 last:border-0">
                <td className="py-2 text-[13px] text-muted">{k}</td>
                <td className="py-2 text-right font-mono text-[15px] font-medium tabular-nums text-ink">
                  {v}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
