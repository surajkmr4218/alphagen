import { useMe } from "./lib/api";

import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/react";
import Dashboard from "./Dashboard";
import LinkPrompt from "./components/LinkPrompt";

import './App.css'



function Gated() {
  const { data: me, isLoading, error } = useMe();
  if (isLoading) return <p className="p-8">Loading…</p>;
  if (error) return <p className="p-8 text-red-600">Failed to load profile.</p>;
  if (!me) return <p className="p-8">Loading…</p>;  // retry-gap: not loading, no error, no data yet
  // Only the owner trades, so only the owner is gated on linking; public
  // (recruiter) users go straight to the read-only demo dashboard.
  if (me.role === "owner" && !me.robinhood_linked) return <LinkPrompt />;
  return <Dashboard me={me} />;
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="flex items-center justify-between border-b bg-white px-6 py-3">
        <h1 className="text-lg font-semibold">AlphaGen</h1>
        <Show when="signed-in">
          <UserButton />
        </Show>
      </header>
      <Show when="signed-out">
        <div className="flex gap-3 p-8">
          <SignInButton mode="modal">
            <button className="rounded bg-black px-4 py-2 text-white">Sign in</button>
          </SignInButton>
          <SignUpButton mode="modal">
            <button className="rounded border px-4 py-2">Create account</button>
          </SignUpButton>
        </div>
      </Show>
      <Show when="signed-in"><Gated /></Show>
    </div>
  );
}