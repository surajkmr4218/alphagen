import type { ReactNode } from "react";
import { Check, X } from "lucide-react";

export type Tone = "up" | "down" | "warn" | "neutral" | "accent";

const tones: Record<Tone, string> = {
  up: "border-up/35 bg-up/10 text-up",
  down: "border-down/35 bg-down/10 text-down",
  warn: "border-warn/35 bg-warn/10 text-warn",
  neutral: "border-edge-bright bg-inset text-muted",
  accent: "border-accent/35 bg-accent/10 text-accent",
};

const dots: Record<Tone, string> = {
  up: "bg-up",
  down: "bg-down",
  warn: "bg-warn",
  neutral: "bg-muted",
  accent: "bg-accent",
};

interface Props {
  tone: Tone;
  children: ReactNode;
  /** Glyph so state never relies on colour alone. `dot` can pulse for live states. */
  glyph?: "check" | "x" | "dot" | "none";
  pulse?: boolean;
  className?: string;
  title?: string;
}

export function Badge({ tone, children, glyph = "none", pulse, className = "", title }: Props) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-px text-xs font-medium whitespace-nowrap ${tones[tone]} ${className}`}
    >
      {glyph === "check" && <Check className="h-3 w-3" strokeWidth={2.5} aria-hidden />}
      {glyph === "x" && <X className="h-3 w-3" strokeWidth={2.5} aria-hidden />}
      {glyph === "dot" && (
        <span
          aria-hidden
          className={`h-1.5 w-1.5 rounded-full ${dots[tone]} ${pulse ? "animate-pulse-dot" : ""}`}
        />
      )}
      {children}
    </span>
  );
}
