import { useCallback, useSyncExternalStore } from "react";

const PATTERN = /^#\/d\/([^/]+)$/;

const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};

const read = () => {
  const m = PATTERN.exec(window.location.hash);
  return m ? decodeURIComponent(m[1]) : null;
};

/**
 * The selected decision lives in the URL hash (`#/d/<id>`) so a trail deep-links,
 * survives refresh, and the browser back button returns to the list on mobile.
 */
export function useSelectedDecision(): [string | null, (id: string | null, opts?: { replace?: boolean }) => void] {
  const id = useSyncExternalStore(subscribe, read, () => null);
  const set = useCallback((next: string | null, opts?: { replace?: boolean }) => {
    const url = window.location.pathname + window.location.search + (next ? `#/d/${encodeURIComponent(next)}` : "");
    if (opts?.replace) window.history.replaceState(null, "", url);
    else window.history.pushState(null, "", url);
    // pushState/replaceState don't emit hashchange; subscribers need a nudge.
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }, []);
  return [id, set];
}
