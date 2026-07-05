import { useQuery } from "@tanstack/react-query";
import { useApi, type Trail } from "../lib/api";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold text-gray-500">{title}</h3>
      {children}
    </section>
  );
}

function Badge({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-semibold text-white ${ok ? "bg-emerald-600" : "bg-rose-600"}`}>
      {children}
    </span>
  );
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
  if (!d) return <div className="p-4 text-gray-400">Loading trail…</div>;

  const diff = d.triggering_diff;
  const hyp = d.hypothesis;
  const critic = d.critic_verdict;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">{d.ticker} — reasoning trail</h2>

      <Section title="Triggering diff">
        {diff ? (
          <>
            <p className="mb-2 text-sm text-gray-600">
              {diff.section} · semantic drift {(diff.semantic_drift * 100).toFixed(0)}% ·{" "}
              {diff.added?.length ?? 0} additions
            </p>
            {(diff.added ?? []).map((s, i) => (
              <p key={i} className="mb-1 rounded bg-emerald-50 px-2 py-1 text-sm">+ {s}</p>
            ))}
            {(diff.removed ?? []).map((s, i) => (
              <p key={i} className="mb-1 rounded bg-rose-50 px-2 py-1 text-sm">− {s}</p>
            ))}
          </>
        ) : (
          <p className="text-sm text-gray-400">No diff recorded.</p>
        )}
      </Section>

      <Section title="Cited passages">
        {d.cited_passages?.length ? (
          d.cited_passages.map((p, i) => (
            <blockquote key={i} className="mb-2 border-l-2 border-gray-300 pl-3 text-sm">
              <p>{p.text}</p>
              <footer className="text-xs text-gray-400">{p.accession} · {p.section}</footer>
            </blockquote>
          ))
        ) : (
          <p className="text-sm text-gray-400">No passages cited.</p>
        )}
      </Section>

      <Section title="Signals">
        {d.signals ? (
          <pre className="overflow-x-auto rounded bg-gray-50 p-2 text-xs">
            {JSON.stringify(d.signals, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-gray-400">No signals recorded.</p>
        )}
      </Section>

      <Section title="Hypothesis">
        {hyp ? (
          <>
            <p className="text-sm">
              <b>{hyp.direction ?? "—"}</b> · ${hyp.size_usd ?? "—"} · {hyp.order_type ?? "—"}
              {hyp.limit_price != null && <> @ ${hyp.limit_price}</>}
              {hyp.confidence != null && <> · conf {(hyp.confidence * 100).toFixed(0)}%</>}
            </p>
            {hyp.rationale && <p className="mt-1 text-sm text-gray-600">{hyp.rationale}</p>}
          </>
        ) : (
          <p className="text-sm text-gray-400">No hypothesis.</p>
        )}
      </Section>

      <Section title="Critic verdict">
        {critic?.verdict ? (
          <>
            <Badge ok={critic.verdict === "accept"}>{critic.verdict.toUpperCase()}</Badge>
            {(critic.reasons ?? []).map((r, i) => (
              <p key={i} className="mt-1 text-sm text-gray-600">— {r}</p>
            ))}
          </>
        ) : (
          <p className="text-sm text-gray-400">No critic verdict.</p>
        )}
      </Section>

      <Section title="Guardrail outcomes">
        {d.guardrail?.results?.length ? (
          d.guardrail.results.map((r, i) => (
            <div key={i} className="mb-1 flex items-center gap-2 text-sm">
              <Badge ok={r.passed}>{r.passed ? "PASS" : r.severity.toUpperCase()}</Badge>
              <span>{r.rule}</span>
              {!r.passed && <span className="text-gray-400">— {r.reason}</span>}
            </div>
          ))
        ) : (
          <p className="text-sm text-gray-400">Not evaluated (dropped before the guardrail).</p>
        )}
      </Section>

      <Section title="Order">
        {d.order ? (
          <p className="text-sm">
            <Badge ok={d.order.status === "filled"}>{d.order.status.toUpperCase()}</Badge>{" "}
            {d.order.quantity != null && <>{d.order.quantity} sh</>}
            {d.order.limit_price != null && <> @ ${d.order.limit_price}</>}
            {d.order.broker_order_id && (
              <span className="text-gray-400"> · ref {d.order.broker_order_id}</span>
            )}
          </p>
        ) : (
          <p className="text-sm text-gray-400">No order — hypothesis did not clear the pipeline.</p>
        )}
      </Section>
    </div>
  );
}
