import { useRef } from "react";

export interface TabItem<T extends string> {
  id: T;
  label: string;
  count?: number;
}

interface Props<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
}

/** Equal-width segmented tabs. The indicator moves by transform, so no measuring. */
export function Tabs<T extends string>({ items, value, onChange, label }: Props<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(0, items.findIndex((t) => t.id === value));

  const move = (next: number) => {
    const i = (next + items.length) % items.length;
    onChange(items[i].id);
    refs.current[i]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className="relative grid rounded-md border border-edge bg-inset p-0.5"
      style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") { e.preventDefault(); move(index + 1); }
        if (e.key === "ArrowLeft") { e.preventDefault(); move(index - 1); }
        if (e.key === "Home") { e.preventDefault(); move(0); }
        if (e.key === "End") { e.preventDefault(); move(items.length - 1); }
      }}
    >
      <span
        aria-hidden
        className="absolute top-0.5 bottom-0.5 left-0.5 rounded-[5px] bg-surface shadow-[inset_0_0_0_1px_var(--color-edge-bright)] transition-transform duration-200 ease-[var(--ease-out-quart)]"
        style={{
          width: `calc((100% - 4px) / ${items.length})`,
          transform: `translateX(${index * 100}%)`,
        }}
      />
      {items.map((t, i) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => { refs.current[i] = el; }}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(t.id)}
            className={`relative z-10 flex h-8 items-center justify-center gap-1 rounded-[5px] px-1 text-xs font-medium transition-colors duration-150 pointer-coarse:h-10 ${
              active ? "text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {t.label}
            {t.count != null && t.count > 0 && (
              <span className={`font-mono text-xs ${active ? "text-accent" : "text-faint"}`}>{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
