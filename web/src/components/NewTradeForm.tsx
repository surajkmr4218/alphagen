import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, useApi, type NewRunResponse, type RunStatus } from "../lib/api";

// makes sure the string is 1 to 5 uppercase letters
const TICKER_RE = /^[A-Z]{1,5}$/;

// Owner-only: the parent Dashboard omponent must not render this for public roles.
// Note the destructuring of props into onSelect which re-renders parent Dashboard component.
export function NewTradeForm({ onSelect }: { onSelect: (decisionId: string) => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const [ticker, setTicker] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [watching, setWatching] = useState<string | null>(null); // decision_id that's being polled

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["decisions"] }),
      qc.invalidateQueries({ queryKey: ["queue"] }),
      qc.invalidateQueries({ queryKey: ["trail"] }),
    ]);

  // useQuery used to poll the submitted run until it lands, then refresh the lists and stop.
  useQuery({
    queryKey: ["run", watching],
    queryFn: async () => {
      const s = await api<RunStatus>(`/owner/runs/${watching}`);
      if (s.status !== "running") {
        setWatching(null);
        setNote(s.status === "failed" ? `Run failed: ${s.reason ?? "unknown error"}` : null);
        await refresh();
      }
      return s;
    },
    enabled: watching != null,
    refetchInterval: 2_500,
  });

  const submit = useMutation({
    mutationFn: (t: string) =>
      api<NewRunResponse>("/owner/hypotheses", {
        method: "POST",
        body: JSON.stringify({ ticker: t }),
      }),
    onSuccess: async (r) => {
      setTicker("");
      setNote(null);
      setWatching(r.decision_id);
      onSelect(r.decision_id);
      await refresh();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        // A run for this ticker is already live so jump to its trail instead of erroring.
        const detail = (err.body as { detail?: { decision_id?: string } })?.detail;
        if (detail?.decision_id) {
          onSelect(detail.decision_id);
          setNote("Already running — showing the existing run.");
          return;
        }
      }
      setNote(err instanceof ApiError && err.status === 422
        ? "Tickers are 1–5 letters."
        : "Could not submit — try again.");
    },
  });

  const valid = TICKER_RE.test(ticker);

  return (
    <section className="panel">
      <h3 className="eyebrow">New trade</h3>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          {/* e.preventDefault() stops the browser's native form submission (which would reload the page) */}
          e.preventDefault();
          if (valid && !submit.isPending) submit.mutate(ticker);
        }}
      >
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase().slice(0, 5))}
          placeholder="TICKER"
          aria-label="Ticker symbol"
          className="w-full min-w-0 rounded-[2px] border border-edge bg-inset px-2.5 py-1.5
                     font-mono text-sm uppercase tracking-wider text-ink
                     placeholder:text-faint focus:border-edge-bright focus:outline-none"
        />
        <button className="btn btn-up" disabled={!valid || submit.isPending}>
          {submit.isPending ? "…" : "Run"}
        </button>
      </form>
      {watching && (
        <p className="mt-2 text-xs text-warn">Analyzing — this can take a few minutes.</p>
      )}
      {note && <p className="mt-2 text-xs text-muted">{note}</p>}
    </section>
  );
}
