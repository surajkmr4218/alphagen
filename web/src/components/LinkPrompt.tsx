import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link2 } from "lucide-react";
import { useApi } from "../lib/api";
import { Button } from "./ui/Button";

export default function LinkPrompt() {
  const api = useApi();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function link() {
    setBusy(true);
    setErr(null);
    try {
      await api("/onboarding/link-robinhood", {
        method: "POST",
        body: JSON.stringify({ access_token: "PLACEHOLDER" }),
      });
      await qc.invalidateQueries({ queryKey: ["me"] }); // only on success
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Link failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-16 flex max-w-md flex-col items-center gap-4 rounded-lg border border-edge bg-surface px-6 py-10 text-center animate-fade-in">
      <span className="flex h-10 w-10 items-center justify-center rounded-full border border-accent/40 bg-accent/10 text-accent">
        <Link2 className="h-5 w-5" aria-hidden />
      </span>
      <h2 className="text-lg font-semibold text-ink">Link your Robinhood account</h2>
      <p className="max-w-sm text-sm text-muted">
        Approved trades are placed through Robinhood, so the account has to be linked before anything can run.
      </p>
      <Button variant="primary" onClick={link} loading={busy}>
        {busy ? "Linking" : "Link Robinhood"}
      </Button>
      {err && <p role="alert" className="text-sm text-down">{err}</p>}
    </div>
  );
}
