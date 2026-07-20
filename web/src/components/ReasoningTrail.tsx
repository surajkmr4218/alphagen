import { useQuery } from "@tanstack/react-query";
import { useApi, type Trail } from "../lib/api";

// A 10-K diff can carry 150+ changed segments per section — render only the first few;
// the header keeps the true totals so nothing is silently hidden.
const MAX_DIFF_SEGMENTS = 10;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h3 className="eyebrow">{title}</h3>
      {children}
    </section>
  );
}

function Badge({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return <span className={`badge ${ok ? "badge-up" : "badge-down"}`}>{children}</span>;
}

// Walks the pipeline top to bottom (diff -> passages -> signals -> hypothesis -> critic ->
// guardrail -> order) so a reader sees WHY the system wanted this trade. Null fields are
// normal (a rejected hypothesis has no order) — each section renders a fallback.
export function ReasoningTrail({ decisionId }: { decisionId: string }) {
  const api = useApi();
  const { data: d } = useQuery({
    queryKey: ["trail", decisionId],
    queryFn: () => api<Trail>(`/decisions/${decisionId}/trail`),
  });
  if (!d) return <div className="p-4 font-mono text-sm text-muted">Loading trail…</div>;

  const diff = d.triggering_diff;
  const hyp = d.hypothesis;
  const critic = d.critic_verdict;

  return (
    <div className="space-y-5">
      <h2 className="flex items-baseline gap-3 border-b border-edge pb-3">
        <span className="font-mono text-2xl font-semibold tracking-tight text-ink">{d.ticker}</span>
        <span className="font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-faint">
          Reasoning Trail
        </span>
      </h2>

      <Section title="Triggering diff">
        {diff ? (
          <>
            <p className="mb-3 font-mono text-xs text-muted">
              {diff.section} · semantic drift{" "}
              <span className="font-semibold text-ink tabular-nums">
                {(diff.semantic_drift * 100).toFixed(0)}%
              </span>{" "}
              · {diff.added?.length ?? 0} additions
            </p>
            {(diff.added ?? []).slice(0, MAX_DIFF_SEGMENTS).map((s, i) => (
              <p
                key={i}
                className="mb-1.5 border-l-2 border-up/60 bg-up/8 px-3 py-1.5 font-mono text-[13px] leading-relaxed text-ink"
              >
                <span className="mr-1 font-semibold text-up">+</span>
                {s}
              </p>
            ))}
            {(diff.added?.length ?? 0) > MAX_DIFF_SEGMENTS && (
              <p className="mb-1.5 font-mono text-xs text-faint">
                … {(diff.added?.length ?? 0) - MAX_DIFF_SEGMENTS} more additions not shown
              </p>
            )}
            {(diff.removed ?? []).slice(0, MAX_DIFF_SEGMENTS).map((s, i) => (
              <p
                key={i}
                className="mb-1.5 border-l-2 border-down/60 bg-down/8 px-3 py-1.5 font-mono text-[13px] leading-relaxed text-muted"
              >
                <span className="mr-1 font-semibold text-down">−</span>
                {s}
              </p>
            ))}
            {(diff.removed?.length ?? 0) > MAX_DIFF_SEGMENTS && (
              <p className="font-mono text-xs text-faint">
                … {(diff.removed?.length ?? 0) - MAX_DIFF_SEGMENTS} more removals not shown
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-faint">No diff recorded.</p>
        )}
      </Section>

      <Section title="Cited passages">
        {d.cited_passages?.length ? (
          d.cited_passages.map((p, i) => (
            <blockquote key={i} className="mb-3 border-l-2 border-edge-bright pl-3 last:mb-0">
              <p className="text-sm leading-relaxed text-ink/90">{p.text}</p>
              <footer className="mt-1 font-mono text-[11px] text-faint">
                {p.accession} · {p.section}
              </footer>
            </blockquote>
          ))
        ) : (
          <p className="text-sm text-faint">No passages cited.</p>
        )}
      </Section>

      <Section title="Signals">
        {d.signals ? (
          <pre className="overflow-x-auto rounded-[2px] border border-edge bg-inset p-3 font-mono text-xs leading-relaxed text-muted">
            {JSON.stringify(d.signals, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-faint">No signals recorded.</p>
        )}
      </Section>

      <Section title="Hypothesis">
        {hyp ? (
          <>
            <p className="font-mono text-sm tabular-nums text-ink">
              <b
                className={
                  hyp.direction === "buy" || hyp.direction === "long"
                    ? "text-up"
                    : hyp.direction === "sell" || hyp.direction === "short"
                      ? "text-down"
                      : ""
                }
              >
                {hyp.direction ?? "—"}
              </b>{" "}
              · ${hyp.size_usd ?? "—"} · {hyp.order_type ?? "—"}
              {hyp.limit_price != null && <> @ ${hyp.limit_price}</>}
              {hyp.confidence != null && <> · conf {(hyp.confidence * 100).toFixed(0)}%</>}
            </p>
            {hyp.rationale && (
              <p className="mt-2 text-sm leading-relaxed text-muted">{hyp.rationale}</p>
            )}
          </>
        ) : (
          <p className="text-sm text-faint">No hypothesis.</p>
        )}
      </Section>

      <Section title="Critic verdict">
        {critic?.verdict ? (
          <>
            <Badge ok={critic.verdict === "accept"}>{critic.verdict.toUpperCase()}</Badge>
            {(critic.reasons ?? []).map((r, i) => (
              <p key={i} className="mt-2 text-sm leading-relaxed text-muted">
                — {r}
              </p>
            ))}
          </>
        ) : (
          <p className="text-sm text-faint">No critic verdict.</p>
        )}
      </Section>

      <Section title="Guardrail outcomes">
        {d.guardrail?.results?.length ? (
          d.guardrail.results.map((r, i) => (
            <div key={i} className="mb-2 flex items-center gap-2.5 text-sm last:mb-0">
              <Badge ok={r.passed}>{r.passed ? "PASS" : r.severity.toUpperCase()}</Badge>
              <span className="font-mono text-[13px] text-ink">{r.rule}</span>
              {!r.passed && <span className="text-faint">— {r.reason}</span>}
            </div>
          ))
        ) : (
          <p className="text-sm text-faint">Not evaluated (dropped before the guardrail).</p>
        )}
      </Section>

      <Section title="Order">
        {d.order ? (
          <>
            <p className="flex items-center gap-2 font-mono text-sm tabular-nums text-ink">
              <Badge ok={d.order.status === "filled"}>{d.order.status.toUpperCase()}</Badge>{" "}
              <span>
                {d.order.quantity != null && <>{d.order.quantity} sh</>}
                {d.order.limit_price != null && <> @ ${d.order.limit_price}</>}
                {d.order.broker_order_id && (
                  <span className="text-faint"> · ref {d.order.broker_order_id}</span>
                )}
              </span>
            </p>
            {d.order.reason && (
              <p className="mt-1.5 text-xs leading-relaxed text-down">— {d.order.reason}</p>
            )}
          </>
        ) : (
          <p className="text-sm text-faint">No order — hypothesis did not clear the pipeline.</p>
        )}
      </Section>
    </div>
  );
}