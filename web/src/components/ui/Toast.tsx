import { useEffect } from "react";
import { Check, AlertTriangle } from "lucide-react";

export interface ToastData {
  id: number;
  message: string;
  tone: "up" | "down" | "neutral";
}

export function Toast({ toast, onDone }: { toast: ToastData | null; onDone: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(onDone, 4000);
    return () => clearTimeout(t);
  }, [toast, onDone]);

  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-0 top-16 z-50 flex justify-center px-4">
      {toast && (
        <div
          key={toast.id}
          className={`animate-rail-in flex items-center gap-2 rounded-md border bg-surface px-3 py-2 text-sm shadow-[0_12px_32px_rgba(0,0,0,0.5)] ${
            toast.tone === "up" ? "border-up/40 text-up"
            : toast.tone === "down" ? "border-down/40 text-down"
            : "border-edge-bright text-ink"
          }`}
        >
          {toast.tone === "up" && <Check className="h-4 w-4" aria-hidden />}
          {toast.tone === "down" && <AlertTriangle className="h-4 w-4" aria-hidden />}
          {toast.message}
        </div>
      )}
    </div>
  );
}
