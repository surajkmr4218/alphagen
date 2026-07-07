import { useMe } from "./lib/api";

import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/react";
import Dashboard from "./Dashboard";
import LinkPrompt from "./components/LinkPrompt";

import './App.css'



function Gated() {
  const { data: me, isLoading, error } = useMe();
  if (isLoading) return <p className="p-8 font-mono text-sm text-muted">Loading…</p>;
  if (error) return <p className="p-8 font-mono text-sm text-down">Failed to load profile.</p>;
  if (!me) return <p className="p-8 font-mono text-sm text-muted">Loading…</p>;  // retry-gap: not loading, no error, no data yet
  // Only the owner trades, so only the owner is gated on linking; public
  // (recruiter) users go straight to the read-only demo dashboard.
  if (me.role === "owner" && !me.robinhood_linked) return <LinkPrompt />;
  return <Dashboard me={me} />;
}

export default function App() {
  return (
    <div className="min-h-screen bg-bg font-sans text-ink">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-edge bg-bg/85 px-6 py-3 backdrop-blur">
        <h1 className="flex items-center gap-2.5 font-mono text-[13px] font-semibold uppercase tracking-[0.22em] text-ink">
          <span
            aria-hidden
            className="inline-block h-2 w-2 bg-up shadow-[0_0_8px_rgba(0,200,150,0.8)]"
          />
          AlphaGen
        </h1>
        <Show when="signed-in">
          <UserButton />
        </Show>
      </header>
      <Show when="signed-out">
        <div className="flex gap-3 p-8">
          <SignInButton mode="modal">
            <button className="btn btn-up">Sign in</button>
          </SignInButton>
          <SignUpButton mode="modal">
            <button className="btn btn-ghost">Create account</button>
          </SignUpButton>
        </div>
      </Show>
      <Show when="signed-in"><Gated /></Show>
    </div>
  );
}