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
    <div className="mx-auto max-w-md p-8 text-center">
      <h2 className="mb-2 text-xl font-semibold">Link your Robinhood account</h2>
      <button
        onClick={link}
        disabled={busy}
        className="rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"
      >
        {busy ? "Linking…" : "Link Robinhood"}
      </button>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
    </div>
  );
}
