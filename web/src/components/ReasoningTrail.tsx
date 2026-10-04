import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApi, type DecisionSummary, type Signals, type Trail } from "../lib/api";
import { ratioPct, relativeTime, signedPct, usd } from "../lib/format";
import { statusView } from "../lib/status";
import { Badge, type Tone } from "./ui/Badge";
import { Skeleton } from "./ui/Skeleton";
import { Stat } from "./ui/Stat";

// A 10-K diff can carry 150+ changed segments per section. Show a few, fold the rest.
const MAX_DIFF_SEGMENTS = 6;

type StageState = "done" | "up" | "down" | "warn" | "running" | "awaiting" | "upcoming" | "skipped";

const node: Record<StageState, string> = {
  done: "border-muted bg-muted",
  up: "border-up bg-up",
  down: "border-down bg-down",
  warn: "border-warn bg-warn",
  running: "border-warn bg-warn animate-pulse-dot",
  awaiting: "border-accent bg-bg shadow-[0_0_0_4px_rgba(143,180,255,0.18)]",
  upcoming: "border-edge-bright bg-bg",
  skipped: "border-dashed border-edge-bright bg-bg",
};

function Stage({
  name, state, meta, index, last, children,
}: { name: string; state: StageState; meta?: ReactNode; index: number; last?: boolean; children?: ReactNode }) {
  const quiet = state === "upcoming" || state === "skipped";
  return (
    <li
      className="relative flex gap-4 pb-8 last:pb-0 animate-rail-in"
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {!last && <span aria-hidden className="absolute top-4 bottom-0 left-[5px] w-px bg-edge" />}
      <span aria-hidden className={`relative mt-[7px] h-[11px] w-[11px] shrink-0 rounded-full border-2 ${node[state]}`} />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <h3 className={`text-[15px] font-medium ${quiet ? "text-faint" : state === "awaiting" ? "text-accent" : "text-ink"}`}>
            {name}
          </h3>
          {meta && <div className="flex items-center gap-2 text-xs text-muted">{meta}</div>}
        </div>
        {children}
      </div>
    </li>
  );
}

function SubHeading({ children }: { children: ReactNode }) {
  return <h4 className="text-xs font-medium text-muted">{children}</h4>;
}

function Quiet({ children }: { children: ReactNode }) {
  return <p className="text-sm text-faint">{children}</p>;
}

function Working() {
  return (
    <div className="flex flex-col gap-2" aria-busy>
      <Skeleton className="h-3.5 w-3/4" />
      <Skeleton className="h-3.5 w-1/2" />
    </div>
  );
}

/* ----------------------------- research ---------------------------------- */

function DiffBlock({ diff }: { diff: NonNullable<Trail["triggering_diff"]> }) {
  const added = diff.added ?? [];
  const removed = diff.removed ?? [];
  const lines = (items: string[], sign: "+" | "−") =>
    items.map((s, i) => (
      <p
        key={`${sign}${i}`}
        className={`quote border-l-2 py-1.5 pr-2 pl-3 text-[14px] ${
          sign === "+" ? "border-up/60 bg-up/6 text-ink" : "border-down/60 bg-down/6 text-muted"
        }`}
      >
        <span className={`mr-2 font-mono text-xs font-medium ${sign === "+" ? "text-up" : "text-down"}`}>{sign}</span>
        {s}
      </p>
    ));
  const hidden = Math.max(0, added.length - MAX_DIFF_SEGMENTS) + Math.max(0, removed.length - MAX_DIFF_SEGMENTS);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span>Section <span className="font-mono text-ink">{diff.section}</span></span>
        <span>Semantic drift <span className="font-mono text-ink">{Math.round(diff.semantic_drift * 100)}%</span></span>
        <span><span className="font-mono text-up">+{added.length}</span> added</span>
        <span><span className="font-mono text-down">−{removed.length}</span> removed</span>
      </div>
      <div className="flex flex-col gap-1.5">
        {lines(added.slice(0, MAX_DIFF_SEGMENTS), "+")}
        {lines(removed.slice(0, MAX_DIFF_SEGMENTS), "−")}
      </div>
      {hidden > 0 && (
        <details className="group">
          <summary className="cursor-pointer list-none text-xs text-accent hover:underline">
            <span className="group-open:hidden">Show {hidden} more</span>
            <span className="hidden group-open:inline">Show fewer</span>
          </summary>
          <div className="mt-1.5 flex flex-col gap-1.5">
            {lines(added.slice(MAX_DIFF_SEGMENTS), "+")}
            {lines(removed.slice(MAX_DIFF_SEGMENTS), "−")}
          </div>
        </details>
      )}
    </div>
  );
}

function PassagesBlock({ passages }: { passages: NonNullable<Trail["cited_passages"]> }) {
  return (
    <ol className="flex flex-col gap-3">
      {passages.map((p, i) => (
        <li key={i} className="border-l-2 border-edge-bright pl-3">
          <p className="quote text-[14px] text-ink/90">{p.text}</p>
          <p className="mt-1 font-mono text-xs text-faint">
            {p.accession} <span className="text-faint/60">/</span> {p.section}
          </p>
        </li>
      ))}
    </ol>
  );
}

const signTone = (v: number | null | undefined): Tone | "ink" => (v == null ? "ink" : v > 0 ? "up" : v < 0 ? "down" : "ink");

function SignalsBlock({ s }: { s: Signals }) {
  const fs = s.financial_scores;
  const ac = s.analyst_consensus;
  const pt = s.price_target;
  const grades = s.recent_grades ?? [];

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Last price" value={s.last_price == null ? "—" : usd(s.last_price)} size="sm" />
        <Stat label="Altman Z" value={fs?.altman_z == null ? "—" : fs.altman_z.toFixed(2)} size="sm" />
        <Stat label="Piotroski" value={fs?.piotroski == null ? "—" : `${fs.piotroski} / 9`} size="sm" />
        <Stat
          label={`Analyst skew${ac?.n ? ` (n=${ac.n})` : ""}`}
          value={ac?.skew == null ? "—" : `${ac.skew > 0 ? "+" : ""}${ac.skew.toFixed(2)}`}
          tone={signTone(ac?.skew)}
          size="sm"
        />
        <Stat label="Target" value={pt?.consensus == null ? "—" : usd(pt.consensus)} size="sm" />
        <Stat
          label="Upside"
          value={pt?.upside == null ? "—" : `${pt.upside > 0 ? "+" : ""}${ratioPct(pt.upside)}`}
          tone={signTone(pt?.upside)}
          size="sm"
        />
      </dl>
      {grades.length > 0 && (
        <ul className="flex flex-col divide-y divide-edge/70 rounded-md border border-edge bg-inset/50 text-[13px]">
          {grades.map((g, i) => {
            const a = (g.action ?? "").toLowerCase();
            const tone: Tone = a.includes("up") ? "up" : a.includes("down") ? "down" : "neutral";
            return (
              <li key={i} className="flex items-center justify-between gap-3 px-3 py-1.5">
                <span className="min-w-0 truncate text-ink">{g.firm ?? "—"}</span>
                <span className="flex items-center gap-2">
                  {g.action && <Badge tone={tone}>{g.action}</Badge>}
                  {g.to && <span className="text-muted">{g.to}</span>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex items-center gap-3">
        {s.bullish_tail != null && (
          <Badge tone={s.bullish_tail ? "up" : "neutral"} glyph={s.bullish_tail ? "check" : "none"}>
            {s.bullish_tail ? "Bullish tail" : "No bullish tail"}
          </Badge>
        )}
        <details className="group">
          <summary className="cursor-pointer list-none text-xs text-faint hover:text-accent">Raw signals</summary>
          <pre className="mt-2 max-w-full overflow-x-auto rounded-md border border-edge bg-inset p-3 font-mono text-xs leading-relaxed text-muted">
            {JSON.stringify(s, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  );
}

/* ------------------------------ the trail -------------------------------- */

function TrailSkeleton() {
  return (
    <ol className="flex flex-col" aria-busy aria-label="Loading trail">
      {Array.from({ length: 6 }).map((_, i) => (
        <li key={i} className="relative flex gap-4 pb-8">
          {i < 5 && <span aria-hidden className="absolute top-4 bottom-0 left-[5px] w-px bg-edge" />}
          <span aria-hidden className="mt-[7px] h-[11px] w-[11px] shrink-0 rounded-full border-2 border-edge bg-bg" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-32" />
            {i < 2 && <Skeleton className="h-3.5 w-3/4" />}
          </div>
        </li>
      ))}
    </ol>
  );
}

interface Props {
  decisionId: string;
  summary?: DecisionSummary;
  live?: boolean;
}

/**
 * Walks the pipeline top to bottom (research, hypothesis, critic, guardrails, the
 * human gate, order) so a reader sees why the system wanted this trade before
 * deciding on it.
 */
export function ReasoningTrail({ decisionId, summary, live = false }: Props) {
  const api = useApi();
  const { data: d, isError } = useQuery({
    queryKey: ["trail", decisionId],
    queryFn: () => api<Trail>(`/decisions/${decisionId}/trail`),
    // Poll only while the decision can still change underneath us.
    refetchInterval: live ? 4_000 : false,
  });

  const hd = summary?.human_decision;
  const running = hd === "running";
  const st = summary ? statusView(summary) : null;

  const header = (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-edge pb-4">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <h2 className="font-mono text-[28px] leading-none font-medium tracking-tight text-ink">
            {d?.ticker ?? summary?.ticker ?? <Skeleton className="inline-block h-7 w-20 align-middle" />}
          </h2>
          {st && <Badge tone={st.tone} glyph={st.glyph} pulse={st.pulse}>{st.label}</Badge>}
        </div>
        <p className="text-xs text-faint">
          Reasoning trail{summary?.created_at && <> · submitted {relativeTime(summary.created_at)}</>}
        </p>
      </div>
      {summary && (summary.entry != null || summary.unrealized_pnl_pct != null) && (
        <dl className="flex items-end gap-5">
          {summary.entry != null && <Stat label="Entry" value={usd(summary.entry)} size="sm" align="right" />}
          {summary.current_price != null && <Stat label="Now" value={usd(summary.current_price)} size="sm" align="right" />}
          {summary.unrealized_pnl_pct != null && (
            <Stat label="Unrealized" value={signedPct(summary.unrealized_pnl_pct)} tone={signTone(summary.unrealized_pnl_pct)} size="sm" align="right" />
          )}
        </dl>
      )}
    </header>
  );

  if (isError) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <p role="alert" className="text-sm text-down">Could not load this trail. It will retry on its own.</p>
      </div>
    );
  }
  if (!d) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <TrailSkeleton />
      </div>
    );
  }

  const diff = d.triggering_diff;
  const hyp = d.hypothesis;
  const critic = d.critic_verdict;
  const rules = d.guardrail?.results ?? [];
  const order = d.order;

  // Stage states. The first stage without data is "running" while the pipeline is
  // live, "skipped" once it has stopped; everything after it follows.
  const researchDone = !!(diff || d.cited_passages?.length || d.signals);
  const after = (prevDone: boolean): StageState => (running ? (prevDone ? "running" : "upcoming") : "skipped");

  const researchState: StageState = researchDone ? "done" : after(true);
  const hypState: StageState = hyp ? "done" : after(researchDone);
  const criticAccept = critic?.verdict === "accept";
  const criticState: StageState = critic?.verdict ? (criticAccept ? "up" : "down") : after(!!hyp);
  const allPassed = rules.length > 0 && rules.every((r) => r.passed) && d.guardrail?.passed !== false;
  const guardState: StageState = rules.length ? (allPassed ? "up" : "down") : after(!!critic?.verdict);

  const gateState: StageState =
    !summary || running ? "upcoming"
    : hd === "pending" ? (summary.passed ? "awaiting" : "skipped")
    : hd === "approved" || hd === "placing" ? "up"
    : "down"; // rejected, failed

  const orderState: StageState =
    order ? (order.status === "filled" ? "up" : order.status === "rejected" ? "down" : "warn")
    : hd === "placing" || hd === "approved" ? "running"
    : gateState === "awaiting" || gateState === "upcoming" ? "upcoming"
    : "skipped";

  const direction = hyp?.direction?.toLowerCase();
  const long = direction === "buy" || direction === "long";
  const failedRules = rules.filter((r) => !r.passed).length;

  return (
    <div className="flex flex-col gap-6">
      {header}
      <ol key={decisionId} className="flex flex-col" aria-label="Pipeline stages">
        <Stage
          index={0}
          name="Research"
          state={researchState}
          meta={diff && <span>{diff.section}</span>}
        >
          {researchState === "running" ? <Working />
          : researchState === "skipped" ? <Quiet>Nothing was retrieved for this run.</Quiet>
          : (
            <div className="flex flex-col gap-5">
              <div className="flex flex-col gap-2">
                <SubHeading>What changed in the filing</SubHeading>
                {diff ? <DiffBlock diff={diff} /> : <Quiet>No diff recorded.</Quiet>}
              </div>
              <div className="flex flex-col gap-2">
                <SubHeading>Cited passages</SubHeading>
                {d.cited_passages?.length ? <PassagesBlock passages={d.cited_passages} /> : <Quiet>No passages cited.</Quiet>}
              </div>
              <div className="flex flex-col gap-2">
                <SubHeading>Market signals</SubHeading>
                {d.signals ? <SignalsBlock s={d.signals} /> : <Quiet>No signals recorded.</Quiet>}
              </div>
            </div>
          )}
        </Stage>

        <Stage
          index={1}
          name="Hypothesis"
          state={hypState}
          meta={hyp?.direction && <Badge tone={long ? "up" : "down"}>{hyp.direction}</Badge>}
        >
          {hypState === "running" ? <Working />
          : !hyp ? <Quiet>{running ? "Not reached yet." : "The analyst abstained. No trade was proposed."}</Quiet>
          : (
            <div className="flex flex-col gap-3">
              <dl className="flex flex-wrap gap-x-6 gap-y-2">
                <Stat label="Size" value={hyp.size_usd == null ? "—" : usd(hyp.size_usd)} size="sm" />
                <Stat label="Order" value={hyp.order_type ?? "—"} size="sm" />
                {hyp.limit_price != null && <Stat label="Limit" value={usd(hyp.limit_price)} size="sm" />}
                {hyp.confidence != null && <Stat label="Confidence" value={`${Math.round(hyp.confidence * 100)}%`} size="sm" />}
              </dl>
              {hyp.rationale && <p className="max-w-[70ch] text-sm leading-relaxed text-ink/90">{hyp.rationale}</p>}
            </div>
          )}
        </Stage>

        <Stage
          index={2}
          name="Critic"
          state={criticState}
          meta={critic?.verdict && (
            <Badge tone={criticAccept ? "up" : "down"} glyph={criticAccept ? "check" : "x"}>{critic.verdict}</Badge>
          )}
        >
          {criticState === "running" ? <Working />
          : !critic?.verdict ? <Quiet>{running ? "Not reached yet." : "No critic verdict."}</Quiet>
          : critic.reasons?.length ? (
            <ul className="flex max-w-[70ch] flex-col gap-1.5 text-sm leading-relaxed text-muted">
              {critic.reasons.map((r, i) => (
                <li key={i} className="flex gap-2"><span aria-hidden className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-faint" />{r}</li>
              ))}
            </ul>
          ) : <Quiet>The critic accepted the thesis without objections.</Quiet>}
        </Stage>

        <Stage
          index={3}
          name="Guardrails"
          state={guardState}
          meta={rules.length > 0 && (
            <span>
              <span className="font-mono text-up">{rules.length - failedRules}</span> pass
              {failedRules > 0 && <>, <span className="font-mono text-down">{failedRules}</span> fail</>}
            </span>
          )}
        >
          {guardState === "running" ? <Working />
          : rules.length === 0 ? <Quiet>{running ? "Not reached yet." : "Not evaluated. The run stopped before the guardrails."}</Quiet>
          : (
            <ul className="flex flex-col divide-y divide-edge/70 rounded-md border border-edge bg-inset/50">
              {rules.map((r, i) => (
                <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-[13px]">
                  <Badge tone={r.passed ? "up" : r.severity === "hard" ? "down" : "warn"} glyph={r.passed ? "check" : "x"} className="w-16 justify-center">
                    {r.passed ? "Pass" : r.severity}
                  </Badge>
                  <span className="font-mono text-ink">{r.rule}</span>
                  {!r.passed && <span className="basis-full text-muted sm:basis-auto">{r.reason}</span>}
                </li>
              ))}
            </ul>
          )}
        </Stage>

        <Stage index={4} name="Your call" state={gateState}>
          <p className={`text-sm ${gateState === "awaiting" ? "text-ink" : "text-muted"}`}>
            {gateState === "awaiting" ? "The pipeline paused here and is waiting for you. Nothing is sent to the broker until you approve."
            : gateState === "upcoming" ? "Not reached yet."
            : gateState === "skipped" ? "Not proposed. The trade did not clear the pipeline, so there was nothing to decide."
            : hd === "rejected" ? "You rejected this trade."
            : hd === "failed" ? "The run failed before it reached you."
            : "You approved this trade."}
          </p>
        </Stage>

        <Stage
          index={5}
          last
          name="Order"
          state={orderState}
          meta={order && (
            <Badge tone={orderState === "warn" || orderState === "running" ? "warn" : orderState as Tone} glyph={orderState === "up" ? "check" : orderState === "down" ? "x" : "dot"} pulse={orderState === "warn" && live}>
              {order.status}
            </Badge>
          )}
        >
          {!order ? (
            <Quiet>
              {orderState === "running" ? "Placing the order with Robinhood."
              : orderState === "upcoming" ? "Placed only after approval."
              : "No order. The hypothesis did not clear the pipeline."}
            </Quiet>
          ) : (
            <div className="flex flex-col gap-2">
              <dl className="flex flex-wrap gap-x-6 gap-y-2">
                {order.quantity != null && <Stat label="Quantity" value={`${order.quantity} sh`} size="sm" />}
                {order.limit_price != null && <Stat label="Limit" value={usd(order.limit_price)} size="sm" />}
                {order.broker_order_id && <Stat label="Broker ref" value={order.broker_order_id} size="sm" />}
              </dl>
              {order.reason && <p className="text-sm text-down">{order.reason}</p>}
            </div>
          )}
        </Stage>
      </ol>
    </div>
  );
}
