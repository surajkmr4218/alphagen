import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "approve" | "reject" | "ghost";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary:
    "border-accent bg-accent text-bg hover:border-[#a9c5ff] hover:bg-[#a9c5ff]",
  approve:
    "border-up/40 bg-up/12 text-up hover:border-up/70 hover:bg-up/20",
  reject:
    "border-edge-bright bg-transparent text-down hover:border-down/60 hover:bg-down/10",
  ghost:
    "border-edge bg-transparent text-muted hover:border-edge-bright hover:bg-surface hover:text-ink",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] pointer-coarse:h-11",
  md: "h-10 px-4 text-sm pointer-coarse:h-11",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "ghost",
  size = "md",
  loading = false,
  icon,
  className = "",
  children,
  disabled,
  ...rest
}: Props) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`press inline-flex items-center justify-center gap-2 rounded-md border font-medium
        transition-[background-color,border-color,color,transform] duration-150
        disabled:opacity-50 ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}
