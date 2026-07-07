import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useApi } from "../lib/api";

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
      await qc.invalidateQueries({ queryKey: ["me"] }); // runs only on success
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Link failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel mx-auto mt-16 max-w-md p-8 text-center">
      <h2 className="mb-4 text-lg font-semibold text-ink">Link your Robinhood account</h2>
      <button onClick={link} disabled={busy} className="btn btn-up">
        {busy ? "Linking…" : "Link Robinhood"}
      </button>
      {err && <p className="mt-3 font-mono text-sm text-down">{err}</p>}
    </div>
  );
}
