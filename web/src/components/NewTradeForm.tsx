import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { ApiError, useApi, type NewRunResponse, type RunStatus } from "../lib/api";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";

// 1 to 5 uppercase letters.
const TICKER_RE = /^[A-Z]{1,5}$/;

// Owner-only: the parent must not render this for public roles.
export function NewTradeForm({ onSelect }: { onSelect: (decisionId: string) => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const inputId = useId();
  const [ticker, setTicker] = useState("");
  const [note, setNote] = useState<{ text: string; tone: "error" | "info" } | null>(null);
  const [watching, setWatching] = useState<string | null>(null); // decision_id being polled

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["decisions"] }),
      qc.invalidateQueries({ queryKey: ["queue"] }),
      qc.invalidateQueries({ queryKey: ["trail"] }),
    ]);

  // Poll the submitted run until it lands, then refresh the lists and stop.
  useQuery({
    queryKey: ["run", watching],
    queryFn: async () => {
      const s = await api<RunStatus>(`/owner/runs/${watching}`);
      if (s.status !== "running") {
        setWatching(null);
        setNote(s.status === "failed" ? { text: `Run failed: ${s.reason ?? "unknown error"}`, tone: "error" } : null);
        await refresh();
      }
      return s;
    },
    enabled: watching != null,
    refetchInterval: 2_500,
  });

  const submit = useMutation({
    mutationFn: (t: string) =>
      api<NewRunResponse>("/owner/hypotheses", { method: "POST", body: JSON.stringify({ ticker: t }) }),
    onSuccess: async (r) => {
      setTicker("");
      setNote(null);
      setWatching(r.decision_id);
      onSelect(r.decision_id);
      await refresh();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        // A run for this ticker is already live: jump to its trail instead of erroring.
        const detail = (err.body as { detail?: { decision_id?: string } })?.detail;
        if (detail?.decision_id) {
          onSelect(detail.decision_id);
          setNote({ text: "Already running. Showing the existing run.", tone: "info" });
          return;
        }
      }
      setNote({
        text: err instanceof ApiError && err.status === 422 ? "Tickers are 1 to 5 letters." : "Could not submit. Try again.",
        tone: "error",
      });
    },
  });

  const valid = TICKER_RE.test(ticker);

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault(); // keep the browser from reloading the page
        if (valid && !submit.isPending) submit.mutate(ticker);
      }}
    >
      <label htmlFor={inputId} className="text-[13px] font-medium text-ink">
        Run a ticker
      </label>
      <div className="flex gap-2">
        <input
          id={inputId}
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase().slice(0, 5))}
          placeholder="MSFT"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          inputMode="text"
          aria-describedby={`${inputId}-help`}
          aria-invalid={note?.tone === "error" || undefined}
          className="h-10 w-full min-w-0 rounded-md border border-edge bg-inset px-3 font-mono text-[15px] uppercase text-ink
                     placeholder:normal-case placeholder:text-faint transition-colors duration-150
                     hover:border-edge-bright focus:border-accent focus:outline-none pointer-coarse:h-11"
        />
        <Button type="submit" variant="primary" loading={submit.isPending} disabled={!valid} icon={<Play className="h-4 w-4" aria-hidden />}>
          Run
        </Button>
      </div>
      <p id={`${inputId}-help`} className="text-xs text-faint">
        1 to 5 letters. Runs the full pipeline, which takes a few minutes.
      </p>
      {watching && (
        <Badge tone="warn" glyph="dot" pulse className="self-start">Analyzing</Badge>
      )}
      {note && (
        <p role={note.tone === "error" ? "alert" : "status"} className={`text-xs ${note.tone === "error" ? "text-down" : "text-muted"}`}>
          {note.text}
        </p>
      )}
    </form>
  );
}
