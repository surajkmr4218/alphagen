import { Show, UserButton } from "@clerk/react";
import { useMe } from "./lib/api";
import Dashboard from "./Dashboard";
import { AccountHeader } from "./components/AccountStrip";
import { Landing } from "./components/Landing";
import LinkPrompt from "./components/LinkPrompt";
import { Button } from "./components/ui/Button";
import { Skeleton } from "./components/ui/Skeleton";

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden>
      <rect width="32" height="32" rx="7" fill="var(--color-surface)" />
      <path d="M16 5 27 16 16 27 5 16Z" fill="none" stroke="var(--color-accent)" strokeWidth="2" strokeLinejoin="round" />
      <path d="M16 11v10M11 16h10" stroke="var(--color-up)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function ShellSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1600px] flex-1 lg:grid lg:grid-cols-[20rem_minmax(0,1fr)]" aria-busy>
      <div className="flex flex-col gap-4 px-4 py-5 lg:border-r lg:border-edge lg:bg-surface lg:px-5">
        <Skeleton className="h-10" />
        <Skeleton className="h-9" />
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[52px]" />)}
      </div>
      <div className="hidden flex-col gap-4 px-8 py-6 lg:flex">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
  );
}

function Gated() {
  const { data: me, isLoading, error, refetch } = useMe();
  if (error) {
    return (
      <div className="mx-auto mt-16 flex max-w-md flex-col items-center gap-3 px-6 text-center">
        <p role="alert" className="text-sm text-down">Could not load your profile.</p>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>Try again</Button>
      </div>
    );
  }
  if (isLoading || !me) return <ShellSkeleton />; // retry gap: not loading, no error, no data yet
  // Only the owner trades, so only the owner is gated on linking.
  if (me.role === "owner" && !me.robinhood_linked) return <LinkPrompt />;
  return <Dashboard me={me} />;
}

export default function App() {
  return (
    <div className="flex min-h-dvh flex-col bg-bg font-sans text-ink">
      <header className="sticky top-0 z-30 border-b border-edge bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between gap-4 px-4 lg:px-5">
          <h1 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-ink">
            <Mark />
            AlphaGen
          </h1>
          <Show when="signed-in">
            <div className="flex min-w-0 items-center gap-4 md:gap-6">
              <AccountHeader />
              <UserButton />
            </div>
          </Show>
        </div>
      </header>
      <Show when="signed-out"><Landing /></Show>
      <Show when="signed-in"><Gated /></Show>
    </div>
  );
}
