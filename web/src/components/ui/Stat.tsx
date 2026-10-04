import type { ReactNode } from "react";
import type { Tone } from "./Badge";

const valueTone: Record<Tone | "ink", string> = {
  up: "text-up",
  down: "text-down",
  warn: "text-warn",
  neutral: "text-muted",
  accent: "text-accent",
  ink: "text-ink",
};

const sizes = {
  sm: "text-[13px]",
  md: "text-base",
  lg: "text-xl",
} as const;

interface Props {
  label: string;
  value: ReactNode;
  tone?: Tone | "ink";
  size?: keyof typeof sizes;
  align?: "left" | "right";
  className?: string;
}

/** A labelled figure. Label is sans, value is mono and tabular. */
export function Stat({ label, value, tone = "ink", size = "md", align = "left", className = "" }: Props) {
  return (
    <div className={`flex min-w-0 flex-col gap-0.5 ${align === "right" ? "items-end text-right" : ""} ${className}`}>
      <span className="text-xs leading-tight text-muted">{label}</span>
      <span className={`font-mono leading-tight font-medium ${sizes[size]} ${valueTone[tone]}`}>{value}</span>
    </div>
  );
}
