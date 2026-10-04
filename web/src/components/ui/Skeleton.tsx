export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div aria-hidden className={`relative overflow-hidden rounded bg-edge/70 ${className}`}>
      <div className="absolute inset-0 animate-shimmer bg-gradient-to-r from-transparent via-white/6 to-transparent" />
    </div>
  );
}
