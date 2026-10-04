import { SignInButton, SignUpButton } from "@clerk/react";
import { Button } from "./ui/Button";

const STAGES: { name: string; detail: string; state: "done" | "gate" | "next" }[] = [
  { name: "Research", detail: "Pulls the 10-K and 10-Q, diffs them against last year, attaches market signals.", state: "done" },
  { name: "Hypothesis", detail: "An analyst model proposes at most one long trade, or abstains, with citations.", state: "done" },
  { name: "Critic", detail: "A second model argues against the thesis. Its verdict is recorded, not binding.", state: "done" },
  { name: "Guardrails", detail: "Deterministic rules: allowlist, exposure caps, rate limits, every citation resolved.", state: "done" },
  { name: "Your call", detail: "The run pauses here. You read the whole trail and approve or reject.", state: "gate" },
  { name: "Order", detail: "Only after approval is the order placed and reconciled against SPY.", state: "next" },
];

/** Signed-out screen. The trail itself is the pitch, so it is the hero. */
export function Landing() {
  return (
    <div className="mx-auto grid max-w-5xl gap-10 px-5 py-12 md:grid-cols-[1.1fr_1fr] md:gap-16 md:px-8 md:py-20 animate-fade-in">
      <div className="flex flex-col gap-6 md:pt-6">
        <h2 className="max-w-[18ch] text-3xl font-semibold leading-tight text-ink md:text-4xl">
          Trades proposed by a model, approved by you.
        </h2>
        <p className="max-w-[52ch] text-[15px] leading-relaxed text-muted">
          AlphaGen reads a company's SEC filings, notices what changed since the last one, and
          writes up a single trade idea with every claim cited back to the filing. A critic pushes
          back, hard rules check it, and then it waits. Nothing reaches the broker until a person
          says so.
        </p>
        <div className="flex flex-wrap gap-3">
          <SignInButton mode="modal">
            <Button variant="primary">Sign in</Button>
          </SignInButton>
          <SignUpButton mode="modal">
            <Button variant="ghost">Create account</Button>
          </SignUpButton>
        </div>
      </div>

      <ol className="relative flex flex-col" aria-label="How a trade moves through AlphaGen">
        {STAGES.map((s, i) => (
          <li
            key={s.name}
            className="relative flex gap-4 pb-6 last:pb-0 animate-rail-in"
            style={{ animationDelay: `${120 + i * 60}ms` }}
          >
            {i < STAGES.length - 1 && <span aria-hidden className="absolute top-4 bottom-0 left-[5px] w-px bg-edge" />}
            <span
              aria-hidden
              className={`relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full border-2 ${
                s.state === "done" ? "border-muted bg-muted"
                : s.state === "gate" ? "border-accent bg-bg shadow-[0_0_0_4px_rgba(143,180,255,0.18)]"
                : "border-edge-bright bg-bg"
              }`}
            />
            <div className="flex flex-col gap-0.5">
              <span className={`text-[15px] font-medium ${s.state === "gate" ? "text-accent" : "text-ink"}`}>{s.name}</span>
              <span className="text-sm leading-relaxed text-muted">{s.detail}</span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
