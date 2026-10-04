import { useState } from "react";

interface Props {
  value: number | null | undefined;
  format: (v: number) => string;
  placeholder?: string;
  className?: string;
}

/**
 * A mono figure that briefly tints green or red when it changes. Direction is
 * derived during render (no effects) and the tint is cleared by onAnimationEnd.
 */
export function FlashValue({ value, format, placeholder = "—", className = "" }: Props) {
  const [prev, setPrev] = useState(value);
  const [flash, setFlash] = useState<{ dir: "up" | "down"; key: number } | null>(null);
  const [tick, setTick] = useState(0);

  if (value !== prev) {
    setPrev(value);
    if (prev != null && value != null) {
      // The key restarts the animation when two changes land inside one flash.
      setTick(tick + 1);
      setFlash({ dir: value > prev ? "up" : "down", key: tick + 1 });
    }
  }

  return (
    <span
      key={flash?.key}
      onAnimationEnd={() => setFlash(null)}
      className={`inline-block rounded px-1 -mx-1 font-mono tabular-nums ${
        flash ? (flash.dir === "up" ? "animate-flash-up" : "animate-flash-down") : ""
      } ${className}`}
    >
      {value == null ? placeholder : format(value)}
    </span>
  );
}
