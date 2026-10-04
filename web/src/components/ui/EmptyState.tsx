import type { ReactNode } from "react";

export function EmptyState({ children, action, className = "" }: { children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-md border border-dashed border-edge-bright px-4 py-5 text-center text-sm text-muted ${className}`}>
      <p>{children}</p>
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  );
}
